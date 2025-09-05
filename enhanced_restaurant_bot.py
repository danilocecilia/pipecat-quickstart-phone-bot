#
# Enhanced DialDish Restaurant Bot with Full Menu Integration
# This file integrates the complete Oishii Windsor menu with Pipecat
#

import os
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
from dotenv import load_dotenv
from loguru import logger

# Import menu integration
from menu_integration import (
    OishiiMenuManager, 
    OrderProcessor, 
    get_enhanced_restaurant_prompt,
    initialize_menu_manager
)

# Pipecat imports (these will work in the quickstart-phone-bot environment)
try:
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.frames.frames import LLMRunFrame
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
    PIPECAT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Pipecat modules not available: {e}")
    logger.warning("This file should be run in the quickstart-phone-bot environment")
    PIPECAT_AVAILABLE = False
    # Create placeholder classes to avoid NameError
    BaseTransport = object
    RunnerArguments = object

load_dotenv(override=True)

# Configuration
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "https://n8n.cvsmart.net/webhook/restaurant-order")
RESTAURANT_NAME = os.getenv("RESTAURANT_NAME", "Oishii Sushi Windsor")

class EnhancedOrderProcessor:
    """Enhanced order processor with full menu integration"""
    
    def __init__(self):
        # Initialize menu manager
        self.menu_manager = initialize_menu_manager()
        self.order_processor = OrderProcessor(self.menu_manager)
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
    
    def extract_customer_info(self, conversation_history):
        """Extract customer information from conversation"""
        customer_info = {"name": "", "phone": "", "email": ""}
        
        # Look through conversation for customer details
        conversation_text = " ".join([msg["content"] for msg in conversation_history])
        
        # Simple regex patterns (would be more sophisticated in production)
        import re
        
        # Look for phone numbers
        phone_pattern = r'\b(\d{3}[-.]?\d{3}[-.]?\d{4})\b'
        phone_match = re.search(phone_pattern, conversation_text)
        if phone_match:
            customer_info["phone"] = phone_match.group(1)
        
        # Look for names (this is very basic - would need better NLP)
        name_patterns = [
            r"my name is (\w+(?:\s+\w+)?)",
            r"this is (\w+(?:\s+\w+)?)",
            r"name[''s]*\s+(\w+(?:\s+\w+)?)"
        ]
        
        for pattern in name_patterns:
            name_match = re.search(pattern, conversation_text, re.IGNORECASE)
            if name_match:
                customer_info["name"] = name_match.group(1).title()
                break
        
        return customer_info
    
    def create_order_data(self, conversation_history):
        """Create structured order data from conversation"""
        # Extract items using the enhanced order processor
        items = self.order_processor.extract_items_from_conversation(conversation_history)
        
        # Extract customer information
        customer_info = self.extract_customer_info(conversation_history)
        
        # Determine order type from conversation
        conversation_text = " ".join([msg["content"] for msg in conversation_history]).lower()
        order_type = "takeout"  # default
        if "dine in" in conversation_text or "dining in" in conversation_text:
            order_type = "dine-in"
        elif "delivery" in conversation_text:
            order_type = "delivery"
        
        # Calculate estimated ready time
        ready_time = datetime.now() + timedelta(minutes=20)
        
        # Extract special instructions
        special_instructions = ""
        if "extra" in conversation_text or "no " in conversation_text or "without" in conversation_text:
            # Could extract more sophisticated instructions
            special_instructions = "See conversation for special requests"
        
        return {
            "customer": customer_info,
            "items": items,
            "order_type": order_type,
            "special_instructions": special_instructions,
            "estimated_ready_time": ready_time.isoformat()
        }

# Global order processor instance
enhanced_order_processor = EnhancedOrderProcessor()

async def run_enhanced_restaurant_bot(transport: BaseTransport):
    """Run the enhanced restaurant bot with full menu integration"""
    logger.info(f"Starting enhanced {RESTAURANT_NAME} bot with full menu integration")

    # Initialize AI services
    stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id=os.getenv("CARTESIA_VOICE_ID", "a0e99841-438c-4a64-b679-ae501e7d6091"),  # Friendly American Female (default)
        # Other voice options:
        # "71a7ad14-091c-4e8e-a314-022ece01c121" - British Reading Lady
        # "2ee87190-8f84-4925-97da-e52547f9462c" - Sarah (Professional)
        # "87748186-23bb-4158-a1eb-332911b0b708" - American Male
    )

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4"  # Use GPT-4 for better restaurant conversations
    )

    # Get the enhanced system prompt with full menu knowledge
    enhanced_prompt = get_enhanced_restaurant_prompt(enhanced_order_processor.menu_manager)

    messages = [
        {
            "role": "system",
            "content": enhanced_prompt,
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
        # Start the conversation with menu-aware greeting
        await task.queue_frame(LLMRunFrame())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Customer disconnected from {RESTAURANT_NAME}")
        
        # Process the order with enhanced menu integration
        try:
            # Get conversation history
            conversation = messages.copy()
            
            # Check if order was completed
            conversation_text = " ".join([msg["content"] for msg in conversation])
            
            order_completion_indicators = [
                "process this order", "order total", "ready for pickup", 
                "thank you for your order", "being prepared", "start preparing"
            ]
            
            if any(phrase in conversation_text.lower() for phrase in order_completion_indicators):
                logger.info("Order appears complete, processing with menu integration...")
                
                # Create structured order data using enhanced processor
                order_data = enhanced_order_processor.create_order_data(conversation)
                
                if order_data["items"]:  # Only send if there are items
                    logger.info(f"Processed order: {order_data}")
                    
                    # Send to n8n workflow
                    result = await enhanced_order_processor.send_order_to_n8n(order_data)
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

async def enhanced_restaurant_bot(runner_args: RunnerArguments):
    """Main enhanced restaurant bot entry point"""
    if not PIPECAT_AVAILABLE:
        logger.error("Pipecat not available. Run this in the quickstart-phone-bot environment.")
        return

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

    await run_enhanced_restaurant_bot(transport)

if __name__ == "__main__":
    if PIPECAT_AVAILABLE:
        from pipecat.runner.run import main
        
        # Override the default bot function
        import sys
        sys.modules[__name__].bot = enhanced_restaurant_bot
        
        main()
    else:
        print("Please run this file in the quickstart-phone-bot environment where Pipecat is installed.")
        print("Copy this file to your quickstart-phone-bot directory and run it there.")
