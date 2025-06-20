from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json
import os
import shutil
import asyncio
import aiohttp
from typing import Dict, List, Optional
import uuid
from datetime import datetime

app = FastAPI(title="niti - Detective Game Backend")

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

# Directories
GAME_DATA_DIR = "/app/game_data"
ASSETS_DIR = "/app/assets"

class GameScript(BaseModel):
    situation: Dict
    people: List[Dict]
    evidence: List[Dict]
    resolution: Dict

class SetupRequest(BaseModel):
    ollama_model: Optional[str] = "gemma3:27b"

class StartGameRequest(BaseModel):
    custom_prompt: Optional[str] = None

def ensure_directories():
    """Ensure required directories exist"""
    os.makedirs(GAME_DATA_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

@app.on_event("startup")
async def startup_event():
    ensure_directories()

@app.post("/api/game/setup")
async def setup_game(setup_request: SetupRequest, background_tasks: BackgroundTasks):
    """Setup phase - install requirements and prepare services"""
    if game_state["current_state"] != "setup":
        raise HTTPException(status_code=400, detail="Game is not in setup state")
    
    background_tasks.add_task(perform_setup, setup_request.ollama_model)
    
    return {"status": "setup_started", "message": "Setting up game requirements..."}

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
            
@app.post("/api/game/start")
async def start_game(start_request: StartGameRequest, background_tasks: BackgroundTasks):
    """Start phase - generate script and assets"""
    if game_state["current_state"] != "ready":
        raise HTTPException(status_code=400, detail="Game is not ready to start")
    
    game_id = str(uuid.uuid4())
    background_tasks.add_task(generate_game_content, game_id, start_request.custom_prompt)
    
    return {"status": "generation_started", "game_id": game_id, "message": "Generating game content..."}

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

สร้างโครงสร้าง JSON ที่มี:
1. situation: {location, time, victim, age, cause_of_death, details}
2. people: array ของตัวละคร โดยแต่ละตัวมี {name, age, role, relationship, characteristics (สำหรับสร้างภาพ), secret, motive, alibi, details}
3. evidence: array ของหลักฐาน โดยแต่ละอันมี {type, description, location, image_generation_prompt}
4. resolution: {culprit, description}

ตอบกลับเป็น JSON ที่ถูกต้องเท่านั้น ไม่ต้องมีคำอธิบายเพิ่มเติม"""
    
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

@app.post("/api/game/restart")
async def restart_game():
    """Restart phase - clear all generated content"""
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
        
        return {"status": "restarted", "message": "Game cleared and ready for setup"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart game: {e}")

@app.get("/api/game/script/{game_id}")
async def get_game_script(game_id: str):
    """Get game script by ID"""
    script_path = os.path.join(GAME_DATA_DIR, f"{game_id}_script.json")
    
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Game script not found")
    
    with open(script_path, 'r', encoding='utf-8') as f:
        script = json.load(f)
    
    return script

@app.get("/api/game/image/{image_id}")
async def get_game_image(image_id: str):
    """Proxy request to Flux service for images"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"http://flux-service:8000/image/{image_id}") as response:
            if response.status == 404:
                raise HTTPException(status_code=404, detail="Image not found")
            
            content = await response.read()
            return Response(content=content, media_type="image/png")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)