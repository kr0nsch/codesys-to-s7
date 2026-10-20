// Линейное масштабирование без ограничения: VALUE вне 0.0…1.0 даёт результат за MIN…MAX
F_ScaleX := rValue * (rMax - rMin) + rMin;
