import logging
import requests
import time
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram import executor
from queue import Queue
from threading import Thread
import io

API_TOKEN = '7110189993:AAHZa7DM6dak3XVrhS0Z0R6GFe5KdKWK2zQ'  # Токен твоего бота

# Список API-ключей Gemini (7 токенов)
API_GEMINI_KEYS = [
    "AIzaSyDxzS_twSmnF9beT9v94SmEwH9EP7NjBHo", 
    "AIzaSyCE9bsPQXgveliU9eyffR1YOL_z5QEWT2E", 
    "AIzaSyAYAQ-8SxkwGVGMPozlQG4fTaFpDeRMADM", 
    "AIzaSyBzfQCDChMv5YcdAKcEmdCXr4-EztJ8IOk", 
    "AIzaSyDaiI_pKXdKksQD-PCJIRkYZxPM9wqqhgs", 
    "AIzaSyBrnujY135GhloN1QtHj4j8Cct6F6dRd4g", 
    "AIzaSyBKz-XkNxGDOd-oCzxIvzL0Rcn-lqDG1u8"
]  # Замените на свои API-ключи

# Настройка логгирования
logging.basicConfig(level=logging.INFO)

# Создание бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Очередь для запросов (размер очереди - 100 запросов)
request_queue = Queue(maxsize=100)

# Словарь для хранения контекста
context = {}

# Функция для обработки запросов в отдельном потоке
def process_requests():
    while True:
        prompt = request_queue.get()
        try:
            user_id = prompt['user_id']  # Получаем ID пользователя из запроса
            request = prompt['request']
            # Попытка получить ответ от Gemini с повтором запроса
            response_text = get_llm_response(request, user_id)
            request_queue.task_done()  # Отметка о завершении обработки
        except Exception as e:
            logging.error(f"Ошибка при обработке запроса: {e}")
            request_queue.task_done()

# Запуск нескольких потоков обработки запросов (количество потоков - 7)
for _ in range(7):
    thread = Thread(target=process_requests)
    thread.daemon = True
    thread.start()

# Функция для получения ответа от модели Gemini с повтором запроса
def get_llm_response(prompt, user_id):
    max_retries = 5  # Максимальное количество повторов
    retry_count = 0
    while retry_count < max_retries:
        for api_key in API_GEMINI_KEYS:
            try:
                with open('prompt.txt', 'r', encoding='utf-8') as file:
                    prompt_content = file.read()
                prompt_with_customization = prompt_content + str(prompt)
                headers = {"Content-Type": "application/json"}
                params = {"key": api_key}
                json_data = {
                    'contents': [
                        {
                            'parts': [{"text": prompt_with_customization}],
                        },
                    ],
                    'generationConfig': {
                        #  'temperature': PRO_TEMPERATURE,
                        # 'topK': 1,
                        # 'topP': 1,
                        'maxOutputTokens': 15000,  # Увеличено до 15000
                        # 'stopSequences': [],
                    },
                    'safetySettings': [
                        {
                            'category': 'HARM_CATEGORY_HARASSMENT',
                            'threshold': 'block_none',
                        },
                        {
                            'category': 'HARM_CATEGORY_HATE_SPEECH',
                            'threshold': 'block_none',
                        },
                        {
                            'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT',
                            'threshold': 'block_none',
                        },
                        {
                            'category': 'HARM_CATEGORY_DANGEROUS_CONTENT',
                            'threshold': 'block_none',
                        },
                    ],
                }
                response = requests.post(
                    'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro-latest:generateContent',
                    params=params,
                    headers=headers,
                    json=json_data,
                )
                response.raise_for_status()  # Проверка кода ответа
                return response.json()['candidates'][0]['content']['parts'][0]['text']
            except requests.exceptions.RequestException as e:
                logging.error(f"Ошибка при отправке запроса к API Gemini: {e}")
                continue  # Переход к следующему API-ключу
        retry_count += 1
        time.sleep(1)  # Пауза перед повторной попыткой
    raise Exception("Не удалось получить ответ от всех API Gemini")

# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.answer("*👋 Добро пожаловать в KingApk | Gemini Pro 1.5!*\n\n*❓ Задайте свой вопрос чтобы я смог на него ответить.*\n\n_ * - если бот долго не отвечает на ваш запрос - попробуйте повторить его :(_", parse_mode="Markdown")

# Обработчик сообщений
@dp.message_handler()
async def echo(message: types.Message):
    prompt = message.text
    user_id = message.from_user.id

    # Сохранение контекста для пользователя
    if user_id not in context:
        context[user_id] = ""

    # Добавление запроса в очередь с ID пользователя
    try:
        request_queue.put({'user_id': user_id, 'request': prompt}, block=False)  
    except queue.Full:
        await message.reply("К сожалению, бот перегружен. Пожалуйста, попробуйте позже.", parse_mode="Markdown")
        return  # Выход из функции

    await bot.send_chat_action(message.chat.id, types.ChatActions.TYPING)

    # Ожидание завершения обработки запроса
    await request_queue.join()

    # Получение ответа из очереди
    try:
        response_text = request_queue.get_nowait()
        if len(response_text) > 2000:  # Проверка длины ответа
            # Создание файла с ответом
            with io.BytesIO(response_text.encode('utf-8')) as file:
                file.name = "ответ.txt"
                await message.reply_document(file)
        else:
            await message.reply(response_text, parse_mode="Markdown")

        # Обновление контекста для пользователя
        context[user_id] = response_text  # Сохранение последнего ответа в контексте
    except queue.Empty:
        await message.reply("Произошла ошибка при обработке вашего запроса. Пожалуйста, повторите попытку позже.", parse_mode="Markdown")
    finally:
        request_queue.task_done()

# Запуск бота
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
