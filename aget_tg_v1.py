import os
import requests
import asyncio
import logging
from functools import lru_cache
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from typing import List, Dict
from dotenv import load_dotenv
import google.generativeai as genai  # Import Google Gemini

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration and Environment Variables
class Config:
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')  # Google Gemini API key
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    COINGECKO_API_URL = os.getenv('COINGECKO_API_URL')
    
    # Rate limiting configuration
    RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW'))
    MAX_REQUESTS_PER_WINDOW = int(os.getenv('MAX_REQUESTS_PER_WINDOW'))

# Initialize Google Gemini
genai.configure(api_key=Config.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')  # Use the Gemini Pro model

# Rate limiting decorator
def rate_limit(func):
    request_times = {}
    
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        current_time = asyncio.get_event_loop().time()
        
        if user_id in request_times:
            recent_requests = [t for t in request_times[user_id] if current_time - t < Config.RATE_LIMIT_WINDOW]
            
            if len(recent_requests) >= Config.MAX_REQUESTS_PER_WINDOW:
                await update.message.reply_text(
                    "Too many requests. Please wait before sending more messages."
                )
                return None
            
            recent_requests.append(current_time)
            request_times[user_id] = recent_requests
        else:
            request_times[user_id] = [current_time]
        
        return await func(update, context)
    
    return wrapper

# Caching for crypto prices with time-based expiration
@lru_cache(maxsize=100)
def get_cached_crypto_prices(crypto_ids: str):
    try:
        params = {
            "ids": crypto_ids,
            "vs_currencies": "usd"
        }
        response = requests.get(Config.COINGECKO_API_URL, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Price fetch error: {e}")
        return {}

# Function to fetch crypto prices for multiple tokens
async def get_crypto_prices(crypto_ids: List[str]) -> str:
    try:
        # Convert list to comma-separated string for caching
        crypto_str = ",".join(crypto_ids).lower()
        data = get_cached_crypto_prices(crypto_str)
        
        prices = []
        for crypto_id in crypto_ids:
            crypto_id = crypto_id.lower()
            if crypto_id in data:
                price = data[crypto_id]["usd"]
                prices.append(f"{crypto_id.upper()}: ${price:.2f} USD")
        
        return "\n".join(prices) if prices else "No prices found."
    
    except Exception as e:
        logger.error(f"Crypto price error: {e}")
        return "Price lookup failed."

# Function to interact with Google Gemini
async def ask_gemini(question: str) -> str:
    # Input validation
    if not question or len(question) > 1000:
        return "Invalid query length."
    
    try:
        # Generate a response using Google Gemini
        # response = model.generate_content(
        #     f"You are an AI assistant focused on cryptocurrency, blockchain, and web3 education. {question}"
        # )
        system_prompt = (
            "You are AgET_TG, a friendly and knowledgeable AI assistant specializing in cryptocurrency, blockchain development and web3 technologies. "
            "Your goal is to educate users and developers, provide accurate information, and assist with crypto-related queries. "
            "Always respond in a clear, concise, and engaging manner. "
            "If a user asks about cryptocurrency prices, fetch the latest data. "
            "For educational questions, explain concepts in simple terms with examples. "
            "Be proactive in suggesting related topics or resources. "
            "Remember to maintain a professional yet approachable tone."
        )
        
        # Generate a response using Google Gemini
        response = model.generate_content(
            f"{system_prompt}\n\nUser: {question}"
        )
        return response.text
    
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return "Gemini query processing failed."

# Start command handler
@rate_limit
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "Hi, I'm AgET_TG, a web3 telegram bot! 🚀\n\n"
        "Commands:\n"
        "- Ask about crypto prices: 'price of bitcoin'\n"
        "- Ask blockchain/crypto questions\n"
        "- Explore Web3 concepts\n"
        "- Build!! \n"
        "- LFG !!"
    )
    await update.message.reply_text(welcome_text)

# Help command handler
@rate_limit
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "AgET_TG Help 📖\n\n"
        "Price Queries:\n"
        "- 'price of bitcoin'\n"
        "- 'price of ethereum, solana'\n\n"
        "Educational Queries:\n"
        "- 'Explain blockchain'\n"
        "- 'How do smart contracts work?'"
    )
    await update.message.reply_text(help_text)

# Message handler
@rate_limit
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text.lower()

    # Check if the user is asking for crypto prices
    if "price of" in user_message:
        # Extract all crypto names from the message
        crypto_names = user_message.split("price of")[-1].strip().split(",")
        crypto_names = [name.strip().lower() for name in crypto_names]
        response = await get_crypto_prices(crypto_names)
    else:
        # Use Google Gemini for other queries
        response = await ask_gemini(user_message)

    await update.message.reply_text(response)

# Error handler
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning(f"Update {update} caused error {context.error}")

# Main function
def main():
    # Validate API keys
    if not Config.GEMINI_API_KEY or not Config.TELEGRAM_BOT_TOKEN:
        logger.error("Missing API keys. Set GEMINI_API_KEY and TELEGRAM_BOT_TOKEN.")
        return

    app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Error handler
    app.add_error_handler(error)

    # Start polling
    logger.info("AgEt_tg started. Press Ctrl+C to stop.")
    app.run_polling(poll_interval=15)

if __name__ == "__main__":
    main()