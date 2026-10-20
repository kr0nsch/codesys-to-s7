# -*- coding: utf-8 -*-
"""Скрипт CODESYS (IronPython 2.7): проект из PLCopen и ST → сборка → (Control Win) прогон и чтение.

Запускает его только tools/codesys/online.py (Python 3) под блокировкой рантайма. Задание — JSON по
пути из переменной C2S7_JOB:
  project, device {type, id, version}, libraries [[имя, разрешение]],
  imports [пути PLCopen], objects [{kind: pou|gvl|dut, name, pou_type, decl, impl}],
  tasks [{name, interval_ms, priority, pous, kind}], build: true,
  exports [{path, objects: [...], application: false}],
  online {credentials, runtime {...}, wait {expr, timeout_s, poll_ms}, read [выражения],
          read_values [{name, exprs}]} — необязательно.
Результат — JSON (поле result задания): сообщения сборки, прочитанные значения (строки read_value),
время чтения. Вход в рантайм — та же последовательность, что в run_tests.py шаблона (функции оттуда).
"""
from __future__ import absolute_import, print_function, unicode_literals

import io
import json
import os
import time
import traceback

import cds_common as C
import run_tests as RT

JOB_ENV = "C2S7_JOB"


def _t(value):
    return C._text(value)


class Log(object):
    def __init__(self):
        self.lines = []

    def info(self, msg):
        self.lines.append("I " + _t(msg))

    def warn(self, msg):
        self.lines.append("W " + _t(msg))


def build_messages():
    se = C.api()
    out = []
    for cat in se.system.get_message_categories():
        for m in se.system.get_message_objects(cat):
            sev = _t(m.severity)
            if sev in ("Text", "Information"):
                continue
            obj = ""
            try:
                obj = _t(m.object.get_name()) if m.object is not None else ""
            except Exception:
                obj = ""
            out.append({"severity": sev, "text": _t(m.text), "object": obj})
    return out


def find_app(proj):
    app = proj.active_application
    if app is not None:
        return app
    for c in proj.get_children(True):
        try:
            if c.is_application:
                return c
        except Exception:
            pass
    raise C.StepError("в проекте нет Application")


def find_named(parent, name):
    for c in parent.get_children(True):
        try:
            if c.get_name() == name:
                return c
        except Exception:
            pass
    return None


def add_libraries(app, libs, log):
    for c in app.get_children(False):
        try:
            if c.is_libman:
                for name, res in libs:
                    c.add_placeholder(name, res)
                    log.info("библиотека #%s -> %s" % (name, res))
        except Exception:
            log.warn("библиотеки: " + traceback.format_exc())


def create_object(app, spec):
    se = C.api()
    kind = spec["kind"]
    name = spec["name"]
    if kind == "gvl":
        obj = app.create_gvl(name)
        obj.textual_declaration.replace(spec["decl"])
        return obj
    if kind == "dut":
        obj = app.create_dut(name)
        obj.textual_declaration.replace(spec["decl"])
        return obj
    types = {
        "program": se.PouType.Program,
        "functionBlock": se.PouType.FunctionBlock,
        "function": se.PouType.Function,
    }
    ptype = types[spec.get("pou_type", "functionBlock")]
    if ptype == se.PouType.Function:
        obj = app.create_pou(name, ptype, return_type=spec.get("return_type") or "INT")
    else:
        obj = app.create_pou(name, ptype)
    obj.textual_declaration.replace(spec["decl"])
    if spec.get("impl") is not None:
        obj.textual_implementation.replace(spec["impl"])
    return obj


def make_tasks(app, tasks, log):
    se = C.api()
    tc = None
    for c in app.get_children(False):
        try:
            if c.get_name() == "Task Configuration":
                tc = c
        except Exception:
            pass
    if tc is None:
        tc = app.create_task_configuration()
    for t in tasks:
        task = tc.create_task(t["name"])
        if t.get("kind") == "freewheeling":
            task.kind_of_task = se.KindOfTask.Freewheeling
        elif t.get("interval_ms") is not None:
            task.interval = _t(t["interval_ms"])
        task.priority = _t(t.get("priority", 1))
        for p in t.get("pous", []):
            task.pous.add(p)
        log.info("задача %s" % t["name"])


def run_online(app, dev, spec, log, result):
    se = C.api()
    creds = RT.read_credentials(spec["credentials"])
    target = RT.setup_gateway(dev, spec.get("runtime", {}), log)
    oa = RT.login(app, dev, creds, target, log)
    reader = RT.Reader(oa, log)
    try:
        oa.start()
        wait = spec.get("wait")
        finished = None
        if wait:
            deadline = time.time() + float(wait.get("timeout_s", 60))
            poll = float(wait.get("poll_ms", 200)) / 1000.0
            while time.time() < deadline:
                raw = reader.raw(wait["expr"])
                if raw is not None and raw.strip().upper() == "TRUE":
                    finished = True
                    break
                se.system.delay(int(poll * 1000))
            result["wait_ok"] = bool(finished)
        values = {}
        for expr in spec.get("read", []):
            values[expr] = reader.raw(expr)
        result["values"] = values
        batches = {}
        for batch in spec.get("read_values", []):
            started = time.time()
            exprs = batch["exprs"]
            raws = None
            try:
                raws = [_t(r) for r in oa.read_values(exprs)]
                how = "read_values"
            except Exception as exc:
                log.warn("read_values: %s" % exc)
                raws = [reader.raw(e) for e in exprs]
                how = "read_value"
            batches[batch["name"]] = {
                "values": raws,
                "seconds": round(time.time() - started, 3),
                "how": how,
                "count": len(exprs),
            }
        result["batches"] = batches
    finally:
        try:
            oa.stop()
        except Exception:
            log.warn("stop: " + traceback.format_exc())
        try:
            oa.logout()
        except Exception:
            log.warn("logout: " + traceback.format_exc())


def main():
    job_path = os.environ.get(JOB_ENV)
    job = json.load(io.open(job_path, encoding="utf-8"))
    log = Log()
    result = {"ok": False}
    try:
        se = C.api()
        project = job["project"]
        if os.path.exists(project):
            os.remove(project)
        C.remove_precompile_cache(project)
        proj = se.projects.create(project, True)
        dev_spec = job["device"]
        proj.add("Device", se.DeviceID(int(dev_spec["type"]), dev_spec["id"], dev_spec["version"]))
        dev = None
        for c in proj.get_children(False):
            try:
                if c.is_device:
                    dev = c
            except Exception:
                pass
        app = find_app(proj)
        add_libraries(app, job.get("libraries", [["Standard", "Standard, * (System)"]]), log)
        imported = []
        for path in job.get("imports", []):
            before = set(c.get_name() for c in app.get_children(True))
            app.import_xml(path)
            after = set(c.get_name() for c in app.get_children(True))
            imported.append({"path": path, "created": sorted(after - before)})
        result["imported"] = imported
        for spec in job.get("objects", []):
            create_object(app, spec)
        if job.get("tasks"):
            make_tasks(app, job["tasks"], log)
        if job.get("build", True):
            app.build()
            msgs = build_messages()
            result["build"] = {
                "errors": len([m for m in msgs if m["severity"] in ("Error", "FatalError")]),
                "warnings": len([m for m in msgs if m["severity"] == "Warning"]),
                "messages": msgs,
            }
        for ex in job.get("exports", []):
            if ex.get("application"):
                proj.export_xml(objects=[app], path=ex["path"], recursive=True)
            else:
                objs = [o for o in (find_named(app, n) for n in ex.get("objects", [])) if o is not None]
                proj.export_xml(objects=objs, path=ex["path"], recursive=True)
        proj.save()
        if job.get("online") and result.get("build", {}).get("errors", 0) == 0:
            run_online(app, dev, job["online"], log, result)
        proj.close()
        result["ok"] = True
    except Exception:
        result["error"] = traceback.format_exc()
    result["log"] = log.lines
    with io.open(job["result"], "w", encoding="utf-8") as fh:
        fh.write(_t(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)))


main()
