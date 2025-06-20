from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
import json
import os
import shutil
import asyncio
import aiohttp
from typing import Dict, List, Optional
import uuid
from datetime import datetime

app = FastAPI(
    title="niti - Detective Game Backend",
    description="AI-powered murder mystery game backend API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Game state
game_state = {
    "current_state": "setup",  # setup, start, playing, restart
    "script_generated": False,
    "assets_generated": False,
    "current_game": None
}

# Chat storage: {game_id: {character_name: [messages]}}
chat_histories = {}

# Directories
GAME_DATA_DIR = "/app/game_data"
ASSETS_DIR = "/app/assets"

class GameScript(BaseModel):
    """Complete murder mystery game script"""
    situation: Dict
    people: List[Dict]
    evidence: List[Dict]
    resolution: Dict

class SetupRequest(BaseModel):
    """Request model for game setup"""
    ollama_model: Optional[str] = "gemma3:27b"

class StartGameRequest(BaseModel):
    """Request model for starting game generation"""
    custom_prompt: Optional[str] = None

class SetupResponse(BaseModel):
    """Response model for setup endpoint"""
    status: str
    message: str

class StartGameResponse(BaseModel):
    """Response model for start game endpoint"""
    status: str
    game_id: str
    message: str

class RestartResponse(BaseModel):
    """Response model for restart endpoint"""
    status: str
    message: str

class GameStateResponse(BaseModel):
    """Response model for game state"""
    current_state: str
    script_generated: bool
    assets_generated: bool
    current_game: Optional[str]

class ChatMessage(BaseModel):
    """Individual chat message"""
    role: str  # 'user' or 'character'
    content: str
    timestamp: datetime

class ChatRequest(BaseModel):
    """Request model for character chat"""
    game_id: str
    character_name: str
    message: str

class ChatResponse(BaseModel):
    """Response model for character chat"""
    character_name: str
    response: str
    timestamp: datetime

class ChatHistoryResponse(BaseModel):
    """Response model for chat history"""
    game_id: str
    character_name: str
    messages: List[ChatMessage]

def ensure_directories():
    """Ensure required directories exist"""
    os.makedirs(GAME_DATA_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

@app.on_event("startup")
async def startup_event():
    ensure_directories()

@app.post("/api/game/setup", response_model=SetupResponse, tags=["Game Management"])
async def setup_game(setup_request: SetupRequest, background_tasks: BackgroundTasks):
    """
    Setup phase - install requirements and prepare services
    
    This endpoint initializes the game by:
    - Checking health of Flux and Ollama services
    - Pulling the specified Ollama model
    - Preparing the game environment
    """
    if game_state["current_state"] != "setup":
        raise HTTPException(status_code=400, detail="Game is not in setup state")
    
    background_tasks.add_task(perform_setup, setup_request.ollama_model)
    
    return SetupResponse(status="setup_started", message="Setting up game requirements...")

async def perform_setup(ollama_model: str):
    """Perform setup tasks"""
    try:
        game_state["current_state"] = "setting_up"
        
        # Check if Flux service is ready
        flux_ready = await check_service_health("http://flux-service:8000/health")
        if not flux_ready:
            raise Exception("Flux service not ready")
        
        # Check if Ollama service is ready
        ollama_ready = await check_service_health("http://ollama-service:11434/api/version")
        if not ollama_ready:
            raise Exception("Ollama service not ready")
        
        # Pull Ollama model if needed
        await pull_ollama_model(ollama_model)
        
        game_state["current_state"] = "ready"
        print("Setup completed successfully")
        
    except Exception as e:
        game_state["current_state"] = "setup_error"
        print(f"Setup failed: {e}")

async def check_service_health(url: str) -> bool:
    """Check if a service is healthy"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                return response.status == 200
    except:
        return False
    
async def pull_ollama_model(model: str):
    """Pull Ollama model"""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://ollama-service:11434/api/pull",
            json={"name": model}
        ) as response:
            if response.status != 200:
                raise Exception(f"Failed to pull model {model}")
            
@app.post("/api/game/start", response_model=StartGameResponse, tags=["Game Management"])
async def start_game(start_request: StartGameRequest, background_tasks: BackgroundTasks):
    """
    Start phase - generate script and assets
    
    This endpoint begins game content generation:
    - Generates murder mystery script using Ollama LLM
    - Creates character images using Flux
    - Generates evidence images
    - Returns unique game ID for tracking
    """
    if game_state["current_state"] != "ready":
        raise HTTPException(status_code=400, detail="Game is not ready to start")
    
    game_id = str(uuid.uuid4())
    background_tasks.add_task(generate_game_content, game_id, start_request.custom_prompt)
    
    return StartGameResponse(status="generation_started", game_id=game_id, message="Generating game content...")

async def generate_game_content(game_id: str, custom_prompt: Optional[str]):
    """Generate game script and assets"""
    try:
        game_state["current_state"] = "generating"
        
        # Generate script using Ollama
        script = await generate_script(custom_prompt)
        
        # Save script
        script_path = os.path.join(GAME_DATA_DIR, f"{game_id}_script.json")
        with open(script_path, 'w', encoding='utf-8') as f:
            json.dump(script, f, ensure_ascii=False, indent=2)
        
        # Generate character images
        await generate_character_images(script["people"], game_id)
        
        # Generate evidence images
        await generate_evidence_images(script["evidence"], game_id)
        
        # Wait for all image generation to complete
        await wait_for_all_images_complete(script)
        
        # Unload Flux model to free memory
        await unload_flux_model()
        
        game_state["current_state"] = "playing"
        game_state["script_generated"] = True
        game_state["assets_generated"] = True
        game_state["current_game"] = game_id
        
        print(f"Game {game_id} generated successfully")
        
    except Exception as e:
        game_state["current_state"] = "generation_error"
        print(f"Game generation failed: {e}")

async def generate_script(custom_prompt: Optional[str]) -> Dict:
    """Generate murder mystery script using Ollama"""
    
    default_prompt = """สร้างบทหนังสืบสวนคดีฆาตรกรรมที่มีความซับซ้อนและน่าติดตาม โดยมีตัวละครหลายตัวที่มีความลับและแรงจูงใจที่แตกต่างกัน เพื่อนำไปใช้เป็นบทของเกมสิบสวน
โดยอ้างอิงจากโครงสร้างที่กำหนดไว้ดังนี้:

{
    "situation": {
        // ส่วนนี้จะเป็นการแนะนำสถานการณ์ก่อนเกิดเหตุและสถานที่เกิดเหตุการณ์
        "location": "ห้องทดลองวิจัยทางวิทยาศาสตร์",
        "time": "คืนวันศุกร์ที่ผ่านมา",
        "victim": "ดร. สมชาย",
        "age": "50",
        "cause_of_death": "ถูกแทงที่หน้าอก",
        "details": "The security guard pointed at the avenue direction and kept uttering 'white clothes'."
    },
    "people": [ // สร้างตัวละครโดยใช้โครงสร้างที่กำหนดไว้ดังนี้:
        // ระบุลักษณะและแรงจูงใจของตัวละคนให้ชัดเจน รวมถึงหลักฐานที่อยู่ของพวกเขาด้วย
        {
            "name": "ดร. อภิชาติ",
            "age": "45",
            "role": "นักวิทยาศาสตร์ที่มีชื่อเสียง",
            "relationship": "เพื่อนร่วมงานของเหยื่อ",
            "characteristics": "{for image generation prompt ex: (A tall, elegant model with beautiful hands and a lovely face, artistically detailed makeup, wearing a long gown with a deep slit and backless dress designs, a delicate necklace with a small diamond pendant, an elegant updo hairstyle to complement the backless gown, a sparkling bracelet to enhance her elegance, and a diamond anklet or a barefoot sandal on her foot, with blonde highlights and shadow in her hair), luxury dinner room environment in the background. night time photo. (High Quality, Detailed Background, Sharp Image:1.24), (Hyper-Detailed:1.15), (Photography, Cinematic Photo, Film-Grain:1.2), (Sharp Photo:1.2) (Taken With A [Pentax 645z | Canon Eos R5]:0.6)}",
            "secret": "เขามีส่วนเกี่ยวข้องกับการทดลองผิดกฎหมายที่อาจเป็นสาเหตุของการฆาตกรรม",
            "motive": "ต้องการปกป้องชื่อเสียงและงานวิจัยของตนเอง",
            "alibi": "อยู่ในห้องทดลองตลอดคืน", // นั้นสามารถเป็นจริง หรือ เท็จก็ได้ และอาจจะขัดแย้งหรือลงตัวกับของคนอื่นก็ได้เช่นกัน รวมถึงสามารถอ้างถึงพยานยินยันที่อยู่ได้
            "details": "เขาเป็นคนที่มีความทะเยอทะยานสูงและไม่สนใจวิธีการที่ใช้ในการบรรลุเป้าหมาย" //  จะถูกนำไปอ้างอิงเพื่อสร้างตัวละคร จะนำไปใช้กับ llm อีกตัวเพื่อแสดงเป็นการสอบสวนตัวละครตัวนั้นๆ จึงต้องระบุอย่างชัดเจน
        }
    ],
    "evidence": [
        // สร้างหลักฐานที่เกี่ยวข้องกับคดีนี้ โดยใช้โครงสร้างที่กำหนด
        {
            "type": "DNA",
            "description": "พบ DNA ของผู้ต้องสงสัยที่เกิดเหตุ",
            "location": "บนเสื้อผ้าของเหยื่อ",
            "image_generation_prompt": "{prompt for image generation make sure it include the details and align with the description ex: Close-up photo of a digital clock covered in frost. Display reads "04:20".}"
        }
    ],
    "resolution": {
        // ส่วนนี้จะเป็นการสรุปผลการสืบสวนและการเปิดเผยความจริง
        "culprit": "ดร. อภิชาติ",
        "description": "เหยื่อถูกวางบนกล่องลิฟต์ ทำให้มีน้ำหนักที่ไม่สามารถมองเห็นได้"
    }
}

เหตุการณ์และตัวละครทั้งหมดด้านบนเป็นเพียงตัวอย่าง คุณสามารถสร้างตัวละครและเหตุการณ์เพิ่มเติมได้ตามต้องการ
เช็คให้แน่ใจว่าเมื่อผู้เล่นอ่านหลักฐาน และสอบถามตัวละคร พวกเขาจะสามารถรวบรวมข้อมูลและเชื่อมโยงเหตุการณ์ต่างๆ เพื่อค้นหาความจริงได้

*GIVEN ME A VALID JSON FORMAT*"""
    
    prompt = custom_prompt if custom_prompt else default_prompt
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://ollama-service:11434/api/generate",
            json={
                "model": "gemma3:27b",
                "prompt": prompt,
                "stream": False,
                "format": "json"
            }
        ) as response:
            if response.status != 200:
                raise Exception("Failed to generate script")
            
            result = await response.json()
            script_text = result["response"]
            
            # Parse JSON response
            try:
                script = json.loads(script_text)
                return script
            except json.JSONDecodeError:
                # If JSON parsing fails, try to extract JSON from the response
                import re
                json_match = re.search(r'\{.*\}', script_text, re.DOTALL)
                if json_match:
                    script = json.loads(json_match.group())
                    return script
                else:
                    raise Exception("Failed to parse generated script as JSON")
                
async def generate_character_images(people: List[Dict], game_id: str):
    """Generate character images using Flux"""
    for i, person in enumerate(people):
        if "characteristics" in person:
            image_id = await request_image_generation(
                person["characteristics"],
                f"{game_id}_character_{i}_{person['name']}"
            )
            person["image_id"] = image_id

async def generate_evidence_images(evidence: List[Dict], game_id: str):
    """Generate evidence images using Flux"""
    for i, item in enumerate(evidence):
        if "image_generation_prompt" in item:
            image_id = await request_image_generation(
                item["image_generation_prompt"],
                f"{game_id}_evidence_{i}_{item['type']}"
            )
            item["image_id"] = image_id

async def request_image_generation(prompt: str, filename: str) -> str:
    """Request image generation from Flux service"""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://flux-service:8000/generate",
            json={
                "prompt": prompt,
                "width": 512,
                "height": 512,
                "filename": filename
            }
        ) as response:
            if response.status != 200:
                raise Exception(f"Failed to generate image for {filename}")
            
            result = await response.json()
            return result["image_id"]

async def wait_for_all_images_complete(script: Dict):
    """Wait for all image generation tasks to complete"""
    image_ids = []
    
    # Collect all image IDs from characters
    for person in script.get("people", []):
        if "image_id" in person:
            image_ids.append(person["image_id"])
    
    # Collect all image IDs from evidence
    for evidence in script.get("evidence", []):
        if "image_id" in evidence:
            image_ids.append(evidence["image_id"])
    
    print(f"Waiting for {len(image_ids)} images to complete generation...")
    
    # Wait for all images to complete
    max_wait_time = 300  # 5 minutes max wait
    check_interval = 5   # Check every 5 seconds
    waited_time = 0
    
    while waited_time < max_wait_time:
        all_complete = True
        
        async with aiohttp.ClientSession() as session:
            for image_id in image_ids:
                async with session.get(f"http://flux-service:8000/status/{image_id}") as response:
                    if response.status == 200:
                        result = await response.json()
                        if result["status"] not in ["completed", "failed"]:
                            all_complete = False
                            break
                    else:
                        all_complete = False
                        break
        
        if all_complete:
            print("All images completed generation")
            break
        
        print(f"Still waiting for images to complete... ({waited_time}s/{max_wait_time}s)")
        await asyncio.sleep(check_interval)
        waited_time += check_interval
    
    if waited_time >= max_wait_time:
        print("Warning: Some images may not have completed generation")

async def unload_flux_model():
    """Unload Flux model from memory to free up resources"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("http://flux-service:8000/unload") as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"Flux model unloading: {result['message']}")
                else:
                    print(f"Failed to unload Flux model: HTTP {response.status}")
    except Exception as e:
        print(f"Error unloading Flux model: {e}")

async def reload_flux_model():
    """Reload Flux model for additional image generation"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("http://flux-service:8000/reload") as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"Flux model reloading: {result['message']}")
                    return True
                else:
                    print(f"Failed to reload Flux model: HTTP {response.status}")
                    return False
    except Exception as e:
        print(f"Error reloading Flux model: {e}")
        return False

@app.post("/api/game/restart", response_model=RestartResponse, tags=["Game Management"])
async def restart_game():
    """
    Restart phase - clear all generated content
    
    This endpoint completely resets the game:
    - Clears all generated scripts and images
    - Resets game state to initial setup
    - Prepares system for new game generation
    """
    try:
        # Clear game data directory
        if os.path.exists(GAME_DATA_DIR):
            shutil.rmtree(GAME_DATA_DIR)
        
        # Clear assets directory
        if os.path.exists(ASSETS_DIR):
            shutil.rmtree(ASSETS_DIR)
        
        # Recreate directories
        ensure_directories()
        
        # Reset game state
        game_state["current_state"] = "setup"
        game_state["script_generated"] = False
        game_state["assets_generated"] = False
        game_state["current_game"] = None
        
        # Clear chat histories
        chat_histories.clear()
        
        return RestartResponse(status="restarted", message="Game cleared and ready for setup")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart game: {e}")

@app.post("/api/flux/unload", tags=["Model Management"])
async def manual_unload_flux():
    """
    Manually unload Flux model to free memory
    
    Useful for freeing GPU memory when not actively generating images.
    The model will be automatically reloaded when needed for new games.
    """
    await unload_flux_model()
    return {"status": "success", "message": "Flux model unload requested"}

@app.post("/api/flux/reload", tags=["Model Management"])
async def manual_reload_flux():
    """
    Manually reload Flux model for image generation
    
    Pre-loads the model into memory for faster image generation.
    This is automatically done when starting new games if needed.
    """
    success = await reload_flux_model()
    if success:
        return {"status": "success", "message": "Flux model reload requested"}
    else:
        return {"status": "error", "message": "Failed to reload Flux model"}

@app.get("/api/game/script/{game_id}", response_model=GameScript, tags=["Game Content"])
async def get_game_script(game_id: str):
    """
    Get game script by ID
    
    Returns the complete murder mystery scenario including:
    - Crime situation details
    - Character profiles with secrets and motives
    - Evidence descriptions
    - Solution and culprit information
    """
    script_path = os.path.join(GAME_DATA_DIR, f"{game_id}_script.json")
    
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Game script not found")
    
    with open(script_path, 'r', encoding='utf-8') as f:
        script = json.load(f)
    
    return script

@app.get("/api/game/image/{image_id}", tags=["Game Content"])
async def get_game_image(image_id: str):
    """
    Get generated game image by ID
    
    Returns AI-generated images for:
    - Character portraits
    - Evidence photographs
    - Scene illustrations
    
    Images are generated using the Flux diffusion model.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://flux-service:8000/image/{image_id}") as response:
            if response.status == 404:
                raise HTTPException(status_code=404, detail="Image not found")
            
            content = await response.read()
            return Response(content=content, media_type="image/png")

async def get_character_context(game_id: str, character_name: str) -> Dict:
    """Get character context from game script"""
    script_path = os.path.join(GAME_DATA_DIR, f"{game_id}_script.json")
    
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Game script not found")
    
    with open(script_path, 'r', encoding='utf-8') as f:
        script = json.load(f)
    
    # Find the character
    character = None
    for person in script.get("people", []):
        if person.get("name") == character_name:
            character = person
            break
    
    if not character:
        raise HTTPException(status_code=404, detail=f"Character '{character_name}' not found")
    
    return {
        "character": character,
        "situation": script.get("situation", {}),
        "all_people": script.get("people", [])
    }

async def generate_character_response(character_context: Dict, chat_history: List[ChatMessage], user_message: str) -> str:
    """Generate character response using LLM"""
    character = character_context["character"]
    situation = character_context["situation"]
    
    # Build conversation context
    character_info = f"""คุณคือ {character['name']} อายุ {character['age']} ปี 
บทบาท: {character['role']}
ความสัมพันธ์กับเหยื่อ: {character['relationship']}
ลักษณะบุคลิก: {character.get('details', '')}
ความลับ: {character['secret']}
แรงจูงใจ: {character['motive']}
ข้อแก้ตัว: {character['alibi']}

สถานการณ์คดี:
สถานที่: {situation.get('location', '')}
เวลา: {situation.get('time', '')}
เหยื่อ: {situation.get('victim', '')}
รายละเอียด: {situation.get('details', '')}

คำแนะนำในการสวมบทบาท:
- ตอบคำถามในฐานะตัวละครนี้
- รักษาความสมจริงตามบุคลิกและบทบาท
- อาจจะเปิดเผยข้อมูลทีละน้อย หรือพยายามปกปิดความลับ
- ตอบเป็นภาษาไทย
- ถ้าถูกถามเรื่องที่ไม่เกี่ยวข้องกับคดี ให้นำกลับมาที่คดีฆาตกรรม
- แสดงอารมณ์และความรู้สึกตามสถานการณ์"""
    
    # Build chat history context
    history_context = ""
    if chat_history:
        history_context = "\n\nประวัติการสนทนา:\n"
        for msg in chat_history[-5:]:  # Last 5 messages for context
            role_name = "ผู้สืบสวน" if msg.role == "user" else character['name']
            history_context += f"{role_name}: {msg.content}\n"
    
    prompt = f"""{character_info}

{history_context}

ผู้สืบสวน: {user_message}

ตอบในฐานะ {character['name']} (ตอบเฉพาะคำพูดของตัวละคร ไม่ต้องมีชื่อหน้า):"""

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://ollama-service:11434/api/generate",
            json={
                "model": "gemma3:27b",
                "prompt": prompt,
                "stream": False
            }
        ) as response:
            if response.status != 200:
                raise Exception("Failed to generate character response")
            
            result = await response.json()
            return result["response"].strip()

@app.post("/api/game/chat", response_model=ChatResponse, tags=["Character Interaction"])
async def chat_with_character(chat_request: ChatRequest):
    """
    Chat with a character from the game
    
    Allows users to have conversations with characters using AI.
    The LLM roleplays as the character based on their profile,
    secrets, motives, and current context.
    """
    if game_state["current_state"] != "playing":
        raise HTTPException(status_code=400, detail="Game is not in playing state")
    
    # Initialize chat history for this game/character if not exists
    if chat_request.game_id not in chat_histories:
        chat_histories[chat_request.game_id] = {}
    
    if chat_request.character_name not in chat_histories[chat_request.game_id]:
        chat_histories[chat_request.game_id][chat_request.character_name] = []
    
    # Get character context
    character_context = await get_character_context(chat_request.game_id, chat_request.character_name)
    
    # Get chat history
    chat_history = chat_histories[chat_request.game_id][chat_request.character_name]
    
    # Add user message to history
    user_message = ChatMessage(
        role="user",
        content=chat_request.message,
        timestamp=datetime.now()
    )
    chat_history.append(user_message)
    
    # Generate character response
    try:
        character_response = await generate_character_response(
            character_context, 
            chat_history, 
            chat_request.message
        )
        
        # Add character response to history
        character_message = ChatMessage(
            role="character",
            content=character_response,
            timestamp=datetime.now()
        )
        chat_history.append(character_message)
        
        return ChatResponse(
            character_name=chat_request.character_name,
            response=character_response,
            timestamp=character_message.timestamp
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate response: {e}")

@app.get("/api/game/chat/{game_id}/{character_name}", response_model=ChatHistoryResponse, tags=["Character Interaction"])
async def get_chat_history(game_id: str, character_name: str):
    """
    Get chat history with a specific character
    
    Returns the conversation history between the user
    and the specified character for the given game.
    """
    if game_id not in chat_histories or character_name not in chat_histories[game_id]:
        return ChatHistoryResponse(
            game_id=game_id,
            character_name=character_name,
            messages=[]
        )
    
    return ChatHistoryResponse(
        game_id=game_id,
        character_name=character_name,
        messages=chat_histories[game_id][character_name]
    )

@app.delete("/api/game/chat/{game_id}", tags=["Character Interaction"])
async def clear_chat_history(game_id: str):
    """
    Clear all chat histories for a game
    
    Removes conversation history for all characters
    in the specified game.
    """
    if game_id in chat_histories:
        del chat_histories[game_id]
    
    return {"status": "cleared", "message": f"Chat history cleared for game {game_id}"}

@app.get("/api/game/characters/{game_id}", tags=["Character Interaction"])
async def get_game_characters(game_id: str):
    """
    Get list of characters available for chat
    
    Returns basic information about all characters
    in the game script for chat interaction.
    """
    script_path = os.path.join(GAME_DATA_DIR, f"{game_id}_script.json")
    
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Game script not found")
    
    with open(script_path, 'r', encoding='utf-8') as f:
        script = json.load(f)
    
    characters = []
    for person in script.get("people", []):
        characters.append({
            "name": person.get("name"),
            "age": person.get("age"),
            "role": person.get("role"),
            "relationship": person.get("relationship"),
            "image_id": person.get("image_id")
        })
    
    return {"characters": characters}

@app.get("/api/game/state", response_model=GameStateResponse, tags=["Game Management"])
async def get_game_state():
    """
    Get current game state
    
    Returns the current state of the game system including:
    - Current phase (setup, ready, generating, playing, etc.)
    - Generation status flags
    - Active game ID if available
    """
    return GameStateResponse(**game_state)

@app.get("/health", tags=["System"])
async def health_check():
    """
    Health check endpoint
    
    Returns the health status of the backend service
    and current game state information.
    """
    return {
        "status": "healthy",
        "service": "niti-backend",
        "version": "1.0.0",
        "game_state": game_state["current_state"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)