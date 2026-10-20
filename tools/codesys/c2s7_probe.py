# -*- coding: utf-8 -*-
"""Проба M0 в CODESYS 3.5.17.30 (IronPython 2.7, запускается host-скриптом tools/probes/run_probes.py).

Задание — JSON по пути из переменной C2S7_JOB:
  {"project": "...", "result": "...", "log": "...",
   "device": {"type": 4096, "id": "0000 0001", "version": "3.5.17.30"},
   "forms": {"dir": "..."},                      # шаг 1: объекты скриптингом -> экспорт PLCopen
   "imports": [{"name": "...", "path": "...", "export": "..."}],   # шаг 2: импорт -> сборка -> экспорт
   "tasks": [{"name": "...", "interval_ms": 10, "priority": 1, "pous": ["..."]}]}
Результат — JSON: что создано, что импортировано, сообщения сборки, пути экспортов.
"""
from __future__ import print_function

import io
import json
import os
import traceback

JOB_ENV = "C2S7_JOB"
LOG = []


def log(msg):
    LOG.append(msg)


def text(value):
    try:
        return unicode(value)
    except NameError:
        return str(value)


def write_json(path, data):
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)))


def build_messages():
    out = []
    for cat in system.get_message_categories():  # noqa: F821
        for m in system.get_message_objects(cat):  # noqa: F821
            sev = text(m.severity)
            if sev in ("Text", "Information"):
                continue
            pos = ""
            try:
                obj = m.object
                pos = text(obj.get_name()) if obj is not None else ""
            except Exception:
                pos = ""
            out.append({"severity": sev, "text": text(m.text), "object": pos})
    return out


def count_summary(msgs):
    errors = len([m for m in msgs if m["severity"] in ("Error", "FatalError")])
    warnings = len([m for m in msgs if m["severity"] == "Warning"])
    return errors, warnings


def find_named(parent, name):
    for c in parent.get_children(True):
        try:
            if c.get_name() == name:
                return c
        except Exception:
            pass
    return None


def make_forms(app, proj, out_dir):
    """Объекты скриптингом: GVL с PERSISTENT, DUT, ФБ с методом/свойством/действием, задачи -> экспорт."""
    res = {"created": [], "exports": {}}
    gvl = app.create_gvl("GVL_Probe")
    gvl.textual_declaration.replace(
        "{attribute 'qualified_only'}\nVAR_GLOBAL\n    xFlag : BOOL;\n    iCount : INT := 5;\nEND_VAR\n"
        "VAR_GLOBAL RETAIN\n    rTotal : REAL;\nEND_VAR\n"
        "VAR_GLOBAL PERSISTENT RETAIN\n    diHours : DINT;\nEND_VAR\n"
    )
    res["created"].append("GVL_Probe")
    dut = app.create_dut("ST_Probe")
    dut.textual_declaration.replace("TYPE ST_Probe :\nSTRUCT\n    a : INT;\n    b : BOOL;\nEND_STRUCT\nEND_TYPE\n")
    res["created"].append("ST_Probe")
    fb = app.create_pou("FB_ProbeOop", PouType.FunctionBlock)  # noqa: F821
    fb.textual_declaration.replace("FUNCTION_BLOCK FB_ProbeOop\nVAR_INPUT\n    xIn : BOOL;\nEND_VAR\nVAR\n    iState : INT;\nEND_VAR\n")
    fb.textual_implementation.replace("iState := iState + 1;\n")
    m = fb.create_method("Reset", "BOOL")
    m.textual_declaration.replace("METHOD Reset : BOOL\nVAR_INPUT\n    iTo : INT;\nEND_VAR\n")
    m.textual_implementation.replace("iState := iTo;\nReset := TRUE;\n")
    p = fb.create_property("State", "INT")
    for acc in p.get_children(False):
        try:
            if acc.get_name() == "Get":
                acc.textual_implementation.replace("State := iState;\n")
            elif acc.get_name() == "Set":
                acc.textual_implementation.replace("iState := State;\n")
        except Exception:
            log("property accessor: " + traceback.format_exc())
    act = fb.create_action("ActClear")
    act.textual_implementation.replace("iState := 0;\n")
    res["created"].append("FB_ProbeOop")
    prg = app.create_pou("PRG_ProbeMain", PouType.Program)  # noqa: F821
    prg.textual_declaration.replace("PROGRAM PRG_ProbeMain\nVAR\n    fbOop : FB_ProbeOop;\nEND_VAR\n")
    prg.textual_implementation.replace("fbOop(xIn := GVL_Probe.xFlag);\nGVL_Probe.diHours := GVL_Probe.diHours + 1;\n")
    res["created"].append("PRG_ProbeMain")
    tc = app.create_task_configuration()
    t1 = tc.create_task("Task_Fast")
    t1.interval = "10"
    t1.priority = "1"
    t1.pous.add("PRG_ProbeMain")
    t2 = tc.create_task("Task_Free")
    try:
        t2.kind_of_task = KindOfTask.Freewheeling  # noqa: F821
    except Exception:
        log("freewheeling: " + traceback.format_exc())
    t2.priority = "20"
    res["created"].append("TaskConfiguration")
    for obj in (gvl, dut, fb, prg):
        path = os.path.join(out_dir, "form_%s.xml" % obj.get_name())
        proj.export_xml(objects=[obj], path=path, recursive=True)
        res["exports"][obj.get_name()] = path
    path = os.path.join(out_dir, "form_Application.xml")
    proj.export_xml(objects=[app], path=path, recursive=True)
    res["exports"]["Application"] = path
    path = os.path.join(out_dir, "form_Application_plain.xml")
    proj.export_xml(objects=[app], path=path, recursive=True, declarations_as_plaintext=True)
    res["exports"]["Application_plain"] = path
    return res


def do_import(app, proj, item):
    """Импорт одного файла в Application (запасной путь — в проект)."""
    before = set(c.get_name() for c in app.get_children(True))
    how = None
    err = None
    try:
        app.import_xml(item["path"])
        how = "application.import_xml(path)"
    except Exception:
        err = traceback.format_exc()
        try:
            proj.import_xml(None, item["path"])
            how = "project.import_xml(None, path)"
        except Exception:
            err = (err or "") + "\n" + traceback.format_exc()
    after = set(c.get_name() for c in app.get_children(True))
    created = sorted(after - before)
    return {"name": item["name"], "how": how, "error": err, "created": created}


def main():
    job_path = os.environ.get(JOB_ENV)
    job = json.load(io.open(job_path, encoding="utf-8"))
    result = {"ok": False, "steps": []}
    try:
        project = job["project"]
        if os.path.exists(project):
            os.remove(project)
        proj = projects.create(project, True)  # noqa: F821
        dev = job["device"]
        proj.add("Device", DeviceID(int(dev["type"]), dev["id"], dev["version"]))  # noqa: F821
        app = proj.active_application
        if app is None:
            for c in proj.get_children(True):
                try:
                    if c.is_application:
                        app = c
                        break
                except Exception:
                    pass
        result["application"] = app.get_name() if app is not None else None
        libs = []
        for c in app.get_children(False):
            try:
                if c.is_libman:
                    for name, res in job.get("libraries", [["Standard", "Standard, * (System)"]]):
                        c.add_placeholder(name, res)
                        libs.append(name)
            except Exception:
                log("libraries: " + traceback.format_exc())
        result["libraries"] = libs
        if job.get("forms"):
            result["forms"] = make_forms(app, proj, job["forms"]["dir"])
            proj.save()
        imports = []
        for item in job.get("imports", []):
            imports.append(do_import(app, proj, item))
        result["imports"] = imports
        if job.get("tasks"):
            tc = None
            for c in app.get_children(False):
                try:
                    if c.get_name() == "Task Configuration":
                        tc = c
                except Exception:
                    pass
            if tc is None:
                tc = app.create_task_configuration()
            for t in job["tasks"]:
                task = tc.create_task(t["name"])
                task.interval = text(t.get("interval_ms", 10))
                task.priority = text(t.get("priority", 1))
                for p in t.get("pous", []):
                    task.pous.add(p)
        if job.get("build", True):
            app.build()
            msgs = build_messages()
            errors, warnings = count_summary(msgs)
            result["build"] = {"errors": errors, "warnings": warnings, "messages": msgs}
        exports = {}
        for item in job.get("imports", []):
            if not item.get("export"):
                continue
            names = item.get("objects") or []
            objs = []
            for n in names:
                o = find_named(app, n)
                if o is not None:
                    objs.append(o)
            if objs:
                proj.export_xml(objects=objs, path=item["export"], recursive=True)
                exports[item["name"]] = {"path": item["export"], "objects": [o.get_name() for o in objs]}
            else:
                exports[item["name"]] = {"path": None, "objects": [], "missing": names}
        result["exports"] = exports
        proj.save()
        proj.close()
        result["ok"] = True
    except Exception:
        result["error"] = traceback.format_exc()
    result["log"] = LOG
    write_json(job["result"], result)


main()
