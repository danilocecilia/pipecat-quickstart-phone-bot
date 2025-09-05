#
# DialDish Restaurant Bot - Pipecat Integration
# This file extends the quickstart-phone-bot to work with the DialDish n8n workflows
#

import os
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame, UserTextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

load_dotenv(override=True)

# DialDish Configuration
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "https://n8n.cvsmart.net/webhook/restaurant-order")
RESTAURANT_NAME = os.getenv("RESTAURANT_NAME", "Oishii Sushi Windsor")

# Restaurant AI Assistant Personality
RESTAURANT_SYSTEM_PROMPT = """
You are Hana, a friendly AI assistant for Oishii Sushi in Windsor, Ontario. Your job is to take phone orders efficiently and accurately.

PERSONALITY:
- Warm, professional, and helpful
- Knowledgeable about Japanese cuisine  
- Patient with customers who need time to decide
- Speak naturally and conversationally

ORDER PROCESS:
1. Greet the customer warmly and introduce yourself
2. Ask if they want dine-in, takeout, or delivery
3. Take their order (ask about quantities, modifications, dietary restrictions)
4. Suggest popular items or chef recommendations if they seem unsure
5. Confirm each item and quantity as you go
6. Calculate and confirm the total (including 13% HST tax)
7. Get customer details (full name, phone number)
8. Provide estimated ready time (usually 15-20 minutes for takeout)
9. End with order confirmation and polite goodbye

MENU HIGHLIGHTS (mention these when appropriate):
- Signature Rolls: Dragon Roll, Rainbow Roll, Philadelphia Roll
- Fresh Sashimi: Salmon, Tuna, Yellowtail
- Popular Appetizers: Gyoza, Edamame, Miso Soup
- Cooked Options: Chicken Teriyaki, Beef Bulgogi, Tempura
- All-You-Can-Eat available for dine-in ($37.99 weekdays, $42.99 weekends)
- Vegetarian options available

PRICING NOTES:
- Most rolls: $8-16
- Sashimi: $3-5 per piece
- Appetizers: $6-12
- Entrees: $16-24
- Add 13% HST to all orders

IMPORTANT RULES:
- Always confirm orders before processing
- Be clear about pricing and tax
- Ask about allergies and dietary restrictions
- Get accurate customer contact information
- If order is complex, repeat it back to customer
- When order is complete, say "Let me process this order for you" and then provide a summary

WHEN ORDER IS COMPLETE:
End the conversation by saying: "Thank you! Your order has been processed and our kitchen will start preparing it right away. Your order total is $X.XX including tax. It will be ready for pickup in approximately X minutes. Have a great day!"
"""

class RestaurantOrderProcessor:
    """Handles order processing and integration with n8n workflow"""
    
    def __init__(self):
        self.current_order = {
            "customer": {"name": "", "phone": "", "email": ""},
            "items": [],
            "order_type": "takeout",
            "special_instructions": "",
            "estimated_ready_time": ""
        }
        
    async def send_order_to_n8n(self, order_data):
        """Send completed order to n8n webhook"""
        try:
            logger.info(f"Sending order to n8n: {order_data}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    N8N_WEBHOOK_URL, 
                    json=order_data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Order successfully sent to n8n: {result}")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(f"Error sending order to n8n: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"Failed to send order to n8n: {e}")
            return None
    
    def parse_order_from_conversation(self, conversation_history):
        """Parse order details from conversation history"""
        # This is a simplified parser - in production, you'd want more sophisticated NLP
        # For now, this demonstrates the structure
        
        order_items = []
        customer_info = {"name": "", "phone": "", "email": ""}
        
        # Extract items (this would be more sophisticated in production)
        conversation_text = " ".join([msg["content"] for msg in conversation_history if msg["role"] in ["user", "assistant"]])
        
        # Sample parsing logic (replace with actual order extraction)
        if "california roll" in conversation_text.lower():
            order_items.append({
                "name": "California Roll",
                "price": 12.99,
                "quantity": 1,
                "modifications": ""
            })
        
        # Calculate estimated ready time (20 minutes from now)
        ready_time = datetime.now() + timedelta(minutes=20)
        
        return {
            "customer": customer_info,
            "items": order_items,
            "order_type": "takeout",
            "special_instructions": "",
            "estimated_ready_time": ready_time.isoformat()
        }

# Global order processor instance
order_processor = RestaurantOrderProcessor()

async def run_restaurant_bot(transport: BaseTransport):
    """Run the restaurant-specific bot with order processing"""
    logger.info(f"Starting {RESTAURANT_NAME} bot")

    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="71a7ad14-091c-4e8e-a314-022ece01c121",  # British Reading Lady
    )

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4"  # Use GPT-4 for better restaurant conversations
    )

    messages = [
        {
            "role": "system",
            "content": RESTAURANT_SYSTEM_PROMPT,
        },
    ]

    context = OpenAILLMContext(messages)
    context_aggregator = llm.create_context_aggregator(context)

    rtvi = RTVIProcessor(config=RTVIConfig(config=[]))

    pipeline = Pipeline(
        [
            transport.input(),  # Transport user input
            rtvi,  # RTVI processor
            stt,
            context_aggregator.user(),  # User responses
            llm,  # LLM
            tts,  # TTS
            transport.output(),  # Transport bot output
            context_aggregator.assistant(),  # Assistant spoken responses
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Customer connected to {RESTAURANT_NAME}")
        # Start the conversation
        greeting = f"Hello! Thank you for calling {RESTAURANT_NAME}. My name is Hana, and I'm here to help you place your order. Are you looking for dine-in, takeout, or delivery today?"
        messages.append({"role": "assistant", "content": greeting})
        await task.queue_frame(LLMRunFrame())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Customer disconnected from {RESTAURANT_NAME}")
        
        # Process the order if the conversation is complete
        try:
            # Get conversation history
            conversation = messages.copy()
            
            # Check if order was completed (look for completion indicators)
            conversation_text = " ".join([msg["content"] for msg in conversation])
            
            if any(phrase in conversation_text.lower() for phrase in [
                "process this order", "order total", "ready for pickup", "thank you for your order"
            ]):
                logger.info("Order appears complete, processing...")
                
                # Parse order from conversation
                order_data = order_processor.parse_order_from_conversation(conversation)
                
                if order_data["items"]:  # Only send if there are items
                    # Send to n8n workflow
                    result = await order_processor.send_order_to_n8n(order_data)
                    if result:
                        logger.info("Order successfully processed and sent to kitchen!")
                    else:
                        logger.error("Failed to process order")
                else:
                    logger.info("No order items found in conversation")
            else:
                logger.info("Conversation ended without completing order")
                
        except Exception as e:
            logger.error(f"Error processing order: {e}")
        
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


async def restaurant_bot(runner_args: RunnerArguments):
    """Main restaurant bot entry point"""

    transport_type, call_data = await parse_telephony_websocket(runner_args.websocket)
    logger.info(f"Auto-detected transport: {transport_type}")

    serializer = TwilioFrameSerializer(
        stream_sid=call_data["stream_id"],
        call_sid=call_data["call_id"],
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
    )

    transport = FastAPIWebsocketTransport(
        websocket=runner_args.websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(),
            serializer=serializer,
        ),
    )

    await run_restaurant_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main
    
    # Override the default bot function
    import sys
    sys.modules[__name__].bot = restaurant_bot
    
    main()
