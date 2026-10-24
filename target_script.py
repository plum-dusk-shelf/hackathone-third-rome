import time
import sys

print("Инициализация системы...")
time.sleep(1)

print("Сбор данных из базы...")
time.sleep(1.5)

for i in range(1, 6):
    print(f"Обработка пакета {i}/5...")
    # Принудительно очищаем буфер вывода Java/Python, чтобы текст отправлялся мгновенно
    sys.stdout.flush() 
    time.sleep(1)

print("Все задачи успешно выполнены!")
