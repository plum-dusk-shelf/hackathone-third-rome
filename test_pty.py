from winpty import PtyProcess

print("Пытаюсь запустить PowerShell через pywinpty...")
try:
    # Пробуем запустить
    proc = PtyProcess.spawn(["powershell.exe", "-NoLogo"])
    print("Успешно! Ждем вывод...")
    
    # Читаем первые данные (должен прийти баннер PS C:\>)
    data = proc.read(1024)
    print("ПОЛУЧЕНО ОТ POWERHELL:")
    print(repr(data))
    
    proc.terminate()
except Exception as e:
    print("ОШИБКА:", e)