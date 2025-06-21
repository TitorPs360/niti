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
    allow_origins=["*"],
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
# Use local directories if /app doesn't exist (development mode)
if os.path.exists("/app"):
    GAME_DATA_DIR = "/app/game_data"
    ASSETS_DIR = "/app/assets"
else:
    GAME_DATA_DIR = "./game_data"
    ASSETS_DIR = "./assets"

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
    extra_prompt: Optional[str] = None

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

class DeductionRequest(BaseModel):
    """Request model for deduction submission"""
    game_id: str
    culprit: str
    reasoning: str

class DeductionResponse(BaseModel):
    """Response model for deduction submission"""
    correct: bool
    score: int  # 0-100
    judgment: str
    actual_culprit: str

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
    background_tasks.add_task(generate_game_content, game_id, start_request.extra_prompt)
    
    return StartGameResponse(status="generation_started", game_id=game_id, message="Generating game content...")

async def generate_game_content(game_id: str, extra_prompt: Optional[str]):
    """Generate game script and assets"""
    try:
        game_state["current_state"] = "generating"
        
        # Generate script using Ollama
        script = await generate_script(extra_prompt)
        
        # Generate character images
        await generate_character_images(script["people"], game_id)
        
        # Generate evidence images
        await generate_evidence_images(script["evidence"], game_id)
        
        # Wait for all image generation to complete
        await wait_for_all_images_complete(script)
        
        # Save script with image_ids
        script_path = os.path.join(GAME_DATA_DIR, f"{game_id}_script.json")
        with open(script_path, 'w', encoding='utf-8') as f:
            json.dump(script, f, ensure_ascii=False, indent=2)
        
        print(f"Script saved with image IDs: {script_path}")
        
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

async def generate_script(extra_prompt: Optional[str]) -> Dict:
    """Generate murder mystery script using Ollama"""
    
    default_prompt = """สร้างบทหนังสืบสวนคดีฆาตรกรรมที่มีความซับซ้อนและน่าติดตาม โดยมีตัวละครหลายตัวที่มีความลับและแรงจูงใจที่แตกต่างกัน เพื่อนำไปใช้เป็นบทของเกมสืบสวน

ข้อกำหนดในการสร้างเนื้อหา (ต้องปฏิบัติตามอย่างเคร่งครัด):
1. ตัวละคร: สร้างตัวละคร **อย่างน้อย 4 คน แต่ไม่เกิน 6 คน** (ห้ามสร้างเพียง 3 คน) แต่ละคนต้องมีความลับที่ซับซ้อน แรงจูงใจที่หลากหลาย และข้อแก้ตัวที่อาจขัดแย้งกัน
2. หลักฐาน: สร้าง 6-10 ชิ้นหลักฐาน แบ่งเป็น:
   - หลักฐานสำคัญ (3-4 ชิ้น): เชื่อมโยงโดยตรงกับผู้กระทำผิดและการฆาตกรรม
   - หลักฐานหลอกลวง (2-3 ชิ้น): ชี้ไปยังผู้ต้องสงสัยคนอื่นแต่เป็นเท็จ
   - หลักฐานเสริม (1-3 ชิ้น): ให้ข้อมูลเพิ่มเติมเกี่ยวกับบุคลิกตัวละครและบริบท
3. ความสัมพันธ์: ตัวละครต้องมีความสัมพันธ์ที่ซับซ้อนและขัดแย้งกัน

โดยอ้างอิงจากโครงสร้างที่กำหนดไว้ดังนี้:

{
    "situation": {
        // ส่วนนี้จะเป็นการแนะนำสถานการณ์ก่อนเกิดเหตุและสถานที่เกิดเหตุการณ์ตามตัวอย่างด้านล่าง
        "location": "โรงแรมหรูแห่งหนึ่งในกรุงเทพ",
        "time": "คืนวันเสาร์ เวลา 22:30 น.",
        "victim": "คุณสมชาย ธนาคาร",
        "age": "45",
        "cause_of_death": "ถูกวางยาพิษในเครื่องดื่ม",
        "details": "เหยื่อเป็นนักธุรกิจที่มีปฏิปักษ์มากมาย พบเสียชีวิตในห้องสูทของโรงแรม"
    },
    "people": [ 
        // สร้างตัวละคร 4-6 คน (ต้องมีอย่างน้อย 4 คน ไม่ใช่แค่ 2-3 คน) โดยแต่ละคนต้องมีความซับซ้อน
        {
            "name": "คุณปัทมา ธนาคาร",
            "age": "38", 
            "role": "ภรรยาของเหยื่อ",
            "relationship": "คู่สมรสที่มีปัญหา",
            "characteristics": "An elegant Thai woman in her late 30s, wearing a sophisticated black evening dress, diamond jewelry, perfectly styled hair in an updo, standing in a luxury hotel lobby, dramatic lighting, professional photography style, high quality, detailed",
            "secret": "เธอมีชู้กับคนขับรถและวางแผนจะหย่าร้าง แต่กลัวว่าจะไม่ได้มรดก",
            "motive": "ต้องการเงินมรดกและเสรีภาพจากชีวิตแต่งงาน",
            "alibi": "อยู่ในห้องน้ำผู้หญิงตอนเกิดเหตุ มีสตาฟโรงแรมเห็น",
            "details": "เป็นคนที่ดูสง่างามภายนอก แต่ข้างในมีความโลภและไร้ยางอาย มักจะแสร้งทำเป็นเศร้าโศกเมื่อพูดถึงสามี"
        },
        {
            "name": "คุณรัชนก บุญมี",
            "age": "29",
            "role": "เลขานุการส่วนตัว",
            "relationship": "ผู้ใต้บังคับบัญชาที่ถูกคุกคาม",
            "characteristics": "A professional Thai woman in her late 20s, wearing a conservative business suit, glasses, holding documents, serious expression, office environment background, corporate photography style",
            "secret": "เธอถูกเหยื่อล่วงละเมิดทางเพศและบังคับให้ทำธุรกิจผิดกฎหมาย",
            "motive": "ต้องการแก้แค้นและหลุดพ้นจากการถูกควบคุม",
            "alibi": "อยู่ที่โต๊ะแถวหน้า พูดคุยกับแขกเข้าร่วมงาน",
            "details": "ดูเป็นคนเงียบขรึม แต่ข้างในเต็มไปด้วยความโกรธแค้น มักจะหลีกเลี่ยงการสบตากับเหยื่อ"
        },
        {
            "name": "คุณวิชัย โชติกุล",
            "age": "45",
            "role": "หุ้นส่วนธุรกิจ",
            "relationship": "เพื่อนร่วมงานและคู่แข่งทางธุรกิจ",
            "characteristics": "A middle-aged Thai businessman in an expensive suit, confident posture, holding a glass of whiskey, luxury office background, professional lighting",
            "secret": "ขโมยเงินจากบริษัทร่วมและเหยื่อกำลังจะเปิดโปง",
            "motive": "กลัวถูกเปิดเผยการทุจริตและต้องการปกป้องการงาน",
            "alibi": "โทรคุยธุรกิจกับลูกค้าต่างประเทศตลอดคืน",
            "details": "ดูเป็นคนมั่นใจและน่าเชื่อถือ แต่จริงๆ แล้วเป็นคนโลภและไม่ซื่อสัตย์"
        },
        {
            "name": "คุณสมหญิง วงษ์ใส",
            "age": "52",
            "role": "แม่บ้านประจำ",
            "relationship": "คนใช้ที่รู้ความลับของครอบครัว",
            "characteristics": "An elderly Thai woman in simple clothing, kind face but worried expression, holding cleaning supplies, modest home interior background",
            "secret": "เธอเป็นพยานในการทะเลาะของเหยื่อกับภรรยาและรู้เรื่องการมีชู้",
            "motive": "กลัวถูกไล่ออกเพราะรู้ความลับมากเกินไป",
            "alibi": "ทำความสะอาดห้องครัวและเห็นทุกคนเข้าออก",
            "details": "เป็นคนซื่อสัตย์แต่กลัวการเปลี่ยนแปลง รู้ความลับของทุกคนในบ้าน"
        }
    ],
    "evidence": [
        // สร้างหลักฐาน 6-120ชิ้น โดยแบ่งประเภทตามความสำคัญ
        {
            "type": "แก้วไวน์ที่มีร่องรอยยาพิษ",
            "description": "แก้วไวน์แดงที่พบในห้องของเหยื่อ มีร่องรอยยาพิษไซยาไนด์ ยังคงมีไวน์เหลืออยู่ครึ่งแก้ว",
            "location": "โต๊ะข้างเตียงในห้องสูท",
            "relevance": "สำคัญ",
            "image_generation_prompt": "Close-up photo of an elegant wine glass with red wine, sitting on a marble table, dramatic lighting, crime scene photography style, high detail",
            "analysis": "หลักฐานหลักที่พิสูจน์วิธีการฆ่า - ยาพิษถูกผสมในไวน์"
        },
        {
            "type": "จดหมายข่มขู่",
            "description": "จดหมายข่มขู่ที่ส่งมาให้เหยื่อเมื่อ 3 วันก่อน เขียนด้วยลายมือที่ดูเหมือนผู้หญิง",
            "location": "ในกระเป๋าเอกสารของเหยื่อ",
            "relevance": "หลอกลวง",
            "image_generation_prompt": "Photo of a threatening letter written in Thai, feminine handwriting, on cream paper, photographed under police investigation lighting",
            "analysis": "ตัวอักษรลายมือหญิงทำให้สงสัยภรรยา แต่จริงๆ แล้วเป็นการปลอมแปลง"
        },
        {
            "type": "ใบเสร็จร้านขายยา",
            "description": "ใบเสร็จซื้อยาขจัดแมลงที่มีส่วนผสมไซยาไนด์ วันที่ซื้อ 2 วันก่อนเกิดเหตุ",
            "location": "ในกระเป๋าถือของเลขานุการ",
            "relevance": "สำคัญ",
            "image_generation_prompt": "Photo of a pharmacy receipt in Thai text, showing pesticide purchase, crumpled paper texture, evidence photography style",
            "analysis": "พิสูจน์ว่าเลขานุการซื้อสารพิษ เป็นหลักฐานสำคัญที่ชี้ตัวผู้กระทำผิด"
        }
    ],
    "resolution": {
        // ต้องมีรายละเอียดครบถ้วนและสมเหตุสมผล รวมถึงการสร้างความประหลาดใจ
        "culprit": "คุณรัชนก บุญมี",
        "description": "แรงจูงใจ: คุณรัชนกถูกเจ้านายล่วงละเมิดทางเพศและบังคับให้ทำธุรกิจผิดกฎหมายมา 2 ปี จนไม่สามารถทนต่อไปได้\n\nการวางแผน: วางแผนฆาตกรรมมา 3 สัปดาห์ โดยศึกษานิสัยการดื่มไวน์ของเจ้านายทุกคืน และศึกษาข้อมูลเกี่ยวกับยาพิษไซยาไนด์จากอินเทอร์เน็ต\n\nการเตรียมการ:\n- ซื้อยาขจัดแมลงที่มีส่วนผสมไซยาไนด์จากร้านขายยาห่างจากที่ทำงาน\n- ปลอมลายมือหญิงเขียนจดหมายข่มขู่เพื่อโยนความผิดไปที่ภรรยา\n- เตรียมไวน์แดงขวดพิเศษที่เจ้านายชอบดื่มทุกคืน\n\nกระบวนการฆาตกรรม: วันเกิดเหตุเวลา 22:15 น. ขณะที่เจ้านายกำลังอาบน้ำ เธอแกะขวดไวน์แดงออก ใส่ผงไซยาไนด์ประมาณ 2 กรัม คนให้เข้ากัน แล้วปิดฝาใหม่ นำไวน์ไปวางไว้บนโต๊ะข้างเตียงตามปกติ รอให้เจ้านายดื่มหลังอาบน้ำเสร็จ เจ้านายเสียชีวิตภายใน 15 นาทีหลังดื่มไวน์เนื่องจากไซยาไนด์ออกฤทธิ์เร็วมาก\n\nการปกปิดหลักฐาน:\n- ทำลายร่องรอยการซื้อยาโดยเผาใบเสร็จปลอม\n- สร้างข้ออ้างว่าอยู่คุยกับแขกงานตลอดเวลา\n- วางจดหมายข่มขู่ลายมือปลอมในกระเป๋าเจ้านายเพื่อโยนความผิดให้ภรรยา\n\nการจัดการหลักฐาน:\n- หลักฐานปลอม: จดหมายข่มขู่ลายมือหญิงเพื่อให้สงสัยภรรยา\n- หลักฐานที่วาง: วางไวน์ที่มีพิษไว้ตามปกติเพื่อไม่ให้น่าสงสัย\n- หลักฐานที่ซ่อน: ซ่อนใบเสร็จจริงในกระเป๋า คิดว่าจะทำลายทีหลัง\n\nข้อผิดพลาดร้อนแรง: ลืมทำลายใบเสร็จจริงที่ซื้อยาขจัดแมลง ยังเก็บไว้ในกระเป๋าถือส่วนตัว ซึ่งกลายเป็นหลักฐานสำคัญที่ชี้ตัวเธอเป็นผู้กระทำผิด"
    }
}

หลักการสำคัญ:
- หลักฐานต้องเชื่อมโยงกันและนำไปสู่ความจริง
- ต้องมีหลักฐานหลอกลวงที่ทำให้ผู้เล่นเข้าใจผิด
- ตัวละครแต่ละคนต้องมีแรงจูงใจที่เข้าใจได้
- การแก้ปริศนาต้องอาศัยการวิเคราะห์หลักฐานและการสอบสวนตัวละคร

ส่วน resolution ต้องมี description ที่รายละเอียดครบถ้วน ประกอบด้วย:
- แรงจูงใจ: เหตุผลที่ชัดเจนและน่าเชื่อ
- การวางแผน: ระยะเวลาและการศึกษาข้อมูลล่วงหน้า
- การเตรียมการ: ขั้นตอนการหาอาวุธ/เครื่องมือ และการเตรียมการอื่นๆ
- กระบวนการฆาตกรรม: เวลาที่แน่นอน, วิธีการฆ่าทีละขั้นตอน, ระยะเวลาที่ใช้
- การปกปิดหลักฐาน: การทำลาย ซ่อน และสร้างข้ออ้าง
- การจัดการหลักฐาน: หลักฐานปลอม, หลักฐานที่วาง, หลักฐานที่ซ่อน
- ข้อผิดพลาดร้อนแรง: สิ่งที่ทำให้ผู้กระทำผิดถูกจับได้

เหตุการณ์และตัวละครด้านบนเป็นเพียงตัวอย่าง คุณสามารถสร้างเรื่องราวใหม่ทั้งหมดได้

**สำคัญมาก: ต้องสร้างตัวละครอย่างน้อย 4 คน ห้ามสร้างเพียง 2-3 คน เด็ดขาด**

เช็คให้แน่ใจว่าเมื่อผู้เล่นอ่านหลักฐานและสอบถามตัวละคร พวกเขาจะสามารถรวบรวมข้อมูลและเชื่อมโยงเหตุการณ์ต่างๆ เพื่อค้นหาความจริงได้

*GIVEN ME A VALID JSON FORMAT*"""
    
    # Combine default prompt with extra prompt if provided
    if extra_prompt:
        prompt = default_prompt + "\n\nเพิ่มเติม: " + extra_prompt
    else:
        prompt = default_prompt
    
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
            filename = f"{game_id}_character_{i}_{person['name']}"
            print(f"Generating character image: {filename}")
            image_id = await request_image_generation(
                person["characteristics"],
                filename
            )
            person["image_id"] = image_id
            print(f"Character image generated: {person['name']} -> {image_id}")
        else:
            print(f"No characteristics found for character: {person.get('name', 'unknown')}")

async def generate_evidence_images(evidence: List[Dict], game_id: str):
    """Generate evidence images using Flux"""
    for i, item in enumerate(evidence):
        if "image_generation_prompt" in item:
            filename = f"{game_id}_evidence_{i}_{item['type']}"
            print(f"Generating evidence image: {filename}")
            image_id = await request_image_generation(
                item["image_generation_prompt"],
                filename
            )
            item["image_id"] = image_id
            print(f"Evidence image generated: {item['type']} -> {image_id}")
        else:
            print(f"No image_generation_prompt found for evidence: {item.get('type', 'unknown')}")

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
    all_people = character_context["all_people"]
    
    # Build other characters info (excluding current character)
    other_characters_info = ""
    for person in all_people:
        if person.get('name') != character['name']:
            other_characters_info += f"""
- {person.get('name', '')}: {person.get('role', '')} (อายุ {person.get('age', '')} ปี)
  ความสัมพันธ์กับเหยื่อ: {person.get('relationship', '')}
  บุคลิก: {person.get('details', '')}"""
    
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

คนอื่นๆ ที่เกี่ยวข้องกับคดี:{other_characters_info}

คำแนะนำในการสวมบทบาท:
- ตอบคำถามในฐานะตัวละครนี้
- เมื่อผู้สืบสวนถามเกี่ยวกับคนอื่น ให้ตอบตามความรู้และความสัมพันธ์ที่คุณมีกับพวกเขา
- ถ้าคุณรู้จักคนนั้น ให้แสดงความรู้สึกและความคิดเห็นตามบุคลิกของคุณ
- ถ้าคุณไม่รู้จักหรือไม่คุ้นเคย ให้บอกตรงๆ ว่าไม่รู้จักดี
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

async def generate_deduction_judgment(script: Dict, guessed_culprit: str, reasoning: str, is_correct: bool) -> str:
    """Generate AI judgment of player's deduction"""
    
    # Gather case information
    situation = script.get("situation", {})
    people = script.get("people", [])
    evidence = script.get("evidence", [])
    resolution = script.get("resolution", {})
    
    # Build character info
    character_info = "\n".join([
        f"- {person.get('name', '')}: {person.get('role', '')} - {person.get('relationship', '')}"
        for person in people
    ])
    
    # Build evidence info
    evidence_info = "\n".join([
        f"- {item.get('type', '')}: {item.get('description', '')} (พบที่: {item.get('location', '')})"
        for item in evidence
    ])
    
    if is_correct:
        prompt = f"""คุณเป็นผู้พิพากษาในเกมสืบสวนคดีฆาตกรรม ผู้เล่นได้ทายผู้ต้องสงสัยถูกต้องแล้ว

ข้อมูลคดี:
สถานที่: {situation.get('location', '')}
เหยื่อ: {situation.get('victim', '')}
สาเหตุการตาย: {situation.get('cause_of_death', '')}

ตัวละคร:
{character_info}

หลักฐาน:
{evidence_info}

ผู้กระทำผิดจริง: {resolution.get('culprit', '')}
วิธีการและแรงจูงใจ: {resolution.get('description', '')}

การทายของผู้เล่น: {guessed_culprit}
เหตุผลของผู้เล่น: {reasoning}

ผู้เล่นทายถูกต้อง! โปรดให้คำตัดสินที่ชื่นชมและอธิบายเรื่องราวความจริงของคดีอย่างละเอียด โดยรวมถึง:

1. การชื่นชมผู้เล่นที่ทายถูก
2. อธิบายลำดับเหตุการณ์ที่เกิดขึ้นจริง:
   - แรงจูงใจและการวางแผนของผู้กระทำผิด
   - ขั้นตอนการเตรียมการฆาตกรรม (วิธีการหาอาวุธ/สารพิษ/เครื่องมือ)
   - รายละเอียดของคืนเกิดเหตุ (เวลาที่แน่นอน, สถานที่, วิธีการลงมือ)
   - วิธีการฆ่าเหยื่อทีละขั้นตอน
   - การปกปิดหลักฐานหรือสร้างข้ออ้างปลอม
3. การวิเคราะห์หลักฐานที่ชี้ไปหาผู้กระทำผิด
4. สิ่งที่จะเกิดขึ้นต่อไป: การจับกุม การสอบสวน และการดำเนินคดี

ใช้ภาษาไทยที่สุภาพและน่าติดตาม เหมือนการเล่าเรื่องสืบสวนที่สมบูรณ์ (ไม่เกิน 400 คำ)"""
    else:
        prompt = f"""คุณเป็นผู้พิพากษาในเกมสืบสวนคดีฆาตกรรม ผู้เล่นได้ทายผู้ต้องสงสัยผิด

ข้อมูลคดี:
สถานที่: {situation.get('location', '')}
เหยื่อ: {situation.get('victim', '')}
สาเหตุการตาย: {situation.get('cause_of_death', '')}

ตัวละคร:
{character_info}

หลักฐาน:
{evidence_info}

ผู้กระทำผิดจริง: {resolution.get('culprit', '')}
วิธีการและแรงจูงใจ: {resolution.get('description', '')}

การทายของผู้เล่น: {guessed_culprit}
เหตุผลของผู้เล่น: {reasoning}

ผู้เล่นทายผิด โปรดให้คำตัดสินที่สุภาพและอธิบายความจริงของคดีอย่างละเอียด โดยรวมถึง:

1. การให้กำลังใจผู้เล่นและบอกว่าการสืบสวนยากมาก
2. เปิดเผยผู้กระทำผิดจริงและอธิบายเหตุใดการทายจึงผิด
3. อธิบายลำดับเหตุการณ์ที่เกิดขึ้นจริง:
   - แรงจูงใจแท้จริงของผู้กระทำผิด
   - ขั้นตอนการเตรียมการฆาตกรรม (วิธีการหาอาวุธ/สารพิษ/เครื่องมือ)
   - รายละเอียดของคืนเกิดเหตุ (เวลาที่แน่นอน, สถานที่, วิธีการลงมือ)
   - วิธีการฆ่าเหยื่อทีละขั้นตอน
   - การปกปิดหลักฐานหรือการหลอกลวง
4. อธิบายหลักฐานที่ชี้ไปหาผู้กระทำผิดจริง และทำไมหลักฐานบางชิ้นจึงเป็นการหลอกลวง
5. สิ่งที่จะเกิดขึ้นต่อไป: การจับกุมผู้กระทำผิดจริง การสอบสวน และการดำเนินคดี

ใช้ภาษาไทยที่สุภาพให้กำลังใจและน่าติดตาม เหมือนการเล่าเรื่องสืบสวนที่สมบูรณ์และอธิบายความจริงของคดีอย่างละเอียด รวมถึงผู้กระทำผิดจริงคือใคร วิธีการฆาตกรรม แรงจูงใจ และการวางแผนของผู้กระทำผิด เพื่อให้ผู้เล่นเข้าใจเหตุการณ์ที่เกิดขึ้นจริงทั้งหมด พร้อมกับอธิบายว่าเหตุใดการทายของผู้เล่นจึงไม่ถูกต้อง และให้กำลังใจ ใช้ภาषาไทย (ไม่เกิน 400 คำ)"""

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
                return "ไม่สามารถประเมินการทายของคุณได้ในขณะนี้"
            
            result = await response.json()
            return result["response"].strip()

async def evaluate_reasoning_quality(script: Dict, reasoning: str) -> int:
    """Evaluate quality of reasoning (0-30 bonus points)"""
    
    evidence = script.get("evidence", [])
    people = script.get("people", [])
    resolution = script.get("resolution", {})
    
    # Build context for evaluation
    evidence_info = "\n".join([
        f"- {item.get('type', '')}: {item.get('description', '')} (ความสำคัญ: {item.get('relevance', 'ไม่ระบุ')})"
        for item in evidence
    ])
    
    character_info = "\n".join([
        f"- {person.get('name', '')}: {person.get('secret', '')} / {person.get('motive', '')}"
        for person in people
    ])
    
    # Get real resolution details
    real_culprit = resolution.get('culprit', '')
    real_resolution = resolution.get('description', '')
    
    prompt = f"""ประเมินคุณภาพของการใช้เหตุผลในการสืบสวน

หลักฐานที่มี:
{evidence_info}

ความลับและแรงจูงใจของตัวละคร:
{character_info}

ความจริงของคดี:
ผู้กระทำผิดจริง: {real_culprit}
รายละเอียดการฆาตกรรม: {real_resolution}

การใช้เหตุผลของผู้เล่น: {reasoning}

ให้คะแนนจาก 0-30 โดยพิจารณา:
- การอ้างอิงหลักฐานที่ถูกต้องและสำคัญ (0-10 คะแนน)
- ความสมเหตุสมผลของการวิเคราะห์ (0-10 คะแนน)  
- ความเข้าใจในกระบวนการฆาตกรรมจริง (0-10 คะแนน)

หลักเกณฑ์การให้คะแนน:
- ถ้าผู้เล่นอ้างอิงหลักฐานสำคัญที่ชี้ไปหาผู้กระทำผิดจริง ให้คะแนนสูง
- ถ้าผู้เล่นเข้าใจกระบวนการฆาตกรรมและการปกปิดหลักฐาน ให้คะแนนสูง
- ถ้าผู้เล่นไม่ตกหลักฐานหลอกลวง ให้คะแนนโบนัส
- ถ้าผู้เล่นอ้างหลักฐานที่ไม่เกี่ยวข้องหรือเข้าใจผิด หักคะแนน

ตอบเฉพาะตัวเลขคะแนนเท่านั้น (เช่น: 25)"""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://ollama-service:11434/api/generate",
                json={
                    "model": "gemma3:27b",
                    "prompt": prompt,
                    "stream": False
                }
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    score_text = result["response"].strip()
                    # Extract number from response
                    import re
                    numbers = re.findall(r'\d+', score_text)
                    if numbers:
                        score = int(numbers[0])
                        return max(0, min(30, score))  # Clamp between 0-30
                
        return 15  # Default bonus if AI evaluation fails
    except:
        return 15  # Default bonus if AI evaluation fails

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

@app.post("/api/game/submit-deduction", response_model=DeductionResponse, tags=["Game Management"])
async def submit_deduction(deduction_request: DeductionRequest):
    """
    Submit deduction and get AI judgment
    
    Player submits their deduction about who the culprit is and their reasoning.
    The system checks against the actual culprit and uses LLM to judge the reasoning quality.
    """
    if game_state["current_state"] != "playing":
        raise HTTPException(status_code=400, detail="Game is not in playing state")
    
    # Get the game script
    script_path = os.path.join(GAME_DATA_DIR, f"{deduction_request.game_id}_script.json")
    
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Game script not found")
    
    with open(script_path, 'r', encoding='utf-8') as f:
        script = json.load(f)
    
    actual_culprit = script.get("resolution", {}).get("culprit", "")
    is_correct = deduction_request.culprit.strip().lower() == actual_culprit.strip().lower()
    
    # Generate AI judgment
    judgment = await generate_deduction_judgment(
        script, 
        deduction_request.culprit, 
        deduction_request.reasoning, 
        is_correct
    )
    
    # Calculate score based on correctness and reasoning quality
    base_score = 70 if is_correct else 20
    reasoning_bonus = await evaluate_reasoning_quality(script, deduction_request.reasoning)
    final_score = min(100, base_score + reasoning_bonus)
    
    return DeductionResponse(
        correct=is_correct,
        score=final_score,
        judgment=judgment,
        actual_culprit=actual_culprit
    )

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