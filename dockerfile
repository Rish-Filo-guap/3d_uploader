FROM python:3.9-slim-buster

# Рабочая директория внутри контейнера
WORKDIR /app

# Копируем файл requirements.txt и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код приложения
COPY . .

# Указываем порт, который будет слушать приложение
EXPOSE 5000

# Команда для запуска приложения
CMD ["python", "main.py"]