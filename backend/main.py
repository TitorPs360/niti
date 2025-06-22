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
        
        # Save script FIRST for review before generating images
        script_path = os.path.join(GAME_DATA_DIR, f"{game_id}_script_raw.json")
        with open(script_path, 'w', encoding='utf-8') as f:
            json.dump(script, f, ensure_ascii=False, indent=2)
        
        print(f"Script generated and saved for review: {script_path}")
        print("Please review the script before continuing with image generation...")
        
        # Generate character images
        await generate_character_images(script["people"], game_id)
        
        # Generate evidence images
        await generate_evidence_images(script["evidence"], game_id)
        
        # Wait for all image generation to complete
        await wait_for_all_images_complete(script)
        
        # Save final script with image_ids
        final_script_path = os.path.join(GAME_DATA_DIR, f"{game_id}_script.json")
        with open(final_script_path, 'w', encoding='utf-8') as f:
            json.dump(script, f, ensure_ascii=False, indent=2)
        
        print(f"Final script saved with image IDs: {final_script_path}")
        
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
    """Generate murder mystery script using Ollama with validation retry"""
    
    default_prompt = """สร้างบทหนังสืบสวนคดีฆาตรกรรมที่มีความซับซ้อนและน่าติดตาม โดยมีตัวละครหลายตัวที่มีความลับและแรงจูงใจที่แตกต่างกัน เพื่อนำไปใช้เป็นบทของเกมสืบสวน

ข้อกำหนดในการสร้างเนื้อหา (ต้องปฏิบัติตามอย่างเคร่งครัด):
1. ตัวละคร: สร้าง **4-6 คน** (ห้าม 3 คน) แต่ละคนมี:
   - ประวัติซับซ้อนมีอดีตที่เชื่อมโยงกับเหยื่อในระยะยาว 
   - มีความลับหลายชั้นที่เกี่ยวเนื่องกัน
   - แรงจูงใจทางจิตวิทยาลึกซึ้ง (ความโกรธ/ความอิจฉา/ความกลัว/ความรัก/ความแค้นที่สะสมมานาน)
   - ความสัมพันธ์ที่เปลี่ยนแปลง (มิตร→ศัตรู, รัก→เกลียด)

2. **กลอุบาย (3-4 กลวิธี)**:
   - ปลอมตัวตน/ประวัติ/หรือซ่อนความจริงระยะยาว
   - ใช้สิ่งแวดล้อม/เสียงธรรมชาติ (ฟ้าร้อง, ดนตรี, เครื่องจักร) ปิดบังการฆ่า
   - จัดการหลักฐานทางกายภาพด้วยวิทยาศาสตร์ (Rigor mortis / การเกร็งตัวของกล้ามเนื้อ, อุณหภูมิศพ, การย่อยสลาย)
   - เลียนแบบคดีเก่า/สร้างฆ่าตัวตายปลอม
   - ใช้ความไว้วางใจ หลอกให้เหยื่อเชื่อใจแล้วโจมตีในช่วงที่ประมาท
   - ใช้เทคโนโลยี/เครื่องมือพิเศษ/อุปกรณ์ตั้งเวลา/เครื่องบันทึกเสียง
   - สร้างข้ออ้างปลอม/โยนความผิดผู้อื่น
   - ใช้ความรู้เฉพาะ (เคมี/การแพทย์/เทคโนโลยี)

3. **แรงจูงใจที่ลึกซึ้งและซับซ้อน**:
   - แก้แค้นข้ามกาลเวลา (เรื่องราวที่เกิดขึ้นหลายปีก่อน แล้วถูกกระตุ้นให้ลุกไหม้อีกครั้ง)
   - ความรักที่ผิดพลาด/ความรักที่ไม่สมหวัง/การหักหลัง/ถูกทอดทิ้ง
   - ความลับครอบครัว (มรดก/รับเลี้ยง/เกียรติยศ)
   - อาชญากรรมในอดีต/ความยุติธรรมที่บิดเบือน
   - การเงิน/ธุรกิจ (หนี้สิน/ล้มละลาย/แบล็กเมล์)
   
4. **หลักฐาน ต้องสร้าง 6-12 ชิ้นเต็ม (ห้ามน้อยกว่า 6 ชิ้น)**:
   - **กายภาพ (3-4 ชิ้น)**: DNA/ลายนิ้วมือ/เครื่องมือฆาตกรรม/ร่องรอยการต่อสู้
   - **จิตวิทยา (2-3 ชิ้น)**: จดหมาย/ไดอารี่/ข้อความ/รูปภาพส่วนตัว
   - **หลอกลวง (2-3 ชิ้น)**: หลักฐานปลอม/ข้อมูลเท็จ/พยานเท็จ
   - **เทคโนโลยี (2-3 ชิ้น)**: บันทึกโทร/CCTV/GPS/ข้อมูลคอมพิวเตอร์
   - แต่ละชิ้นต้องมี: type, description, location, relevance, image_generation_prompt, analysis
   - **relevance ต้องเป็นหนึ่งในสี่ประเภทนี้เท่านั้น: "กายภาพ", "จิตวิทยา", "หลอกลวง", "เทคโนโลยี"**
   - image_generation_prompt ต้องเป็นภาษาอังกฤษเท่านั้น **NEED TO BE IN ENGLISH** เพื่อให้สามารถสร้างภาพได้

5. ความสัมพันธ์: ซับซ้อนขัดแย้ง มีศัตรูหลายคน เพื่อให้โยนความผิดได้

โดยอ้างอิงจากโครงสร้างที่กำหนดไว้ดังนี้:

{
    "situation": {
        // ส่วนนี้จะเป็นการแนะนำสถานการณ์ก่อนเกิดเหตุและสถานที่เกิดเหตุการณ์ตามตัวอย่างด้านล่าง
        "location": "โรงแรมหรูแห่งหนึ่งในกรุงเทพ", // สถานที่ที่มีความหมายพิเศษกับตัวละคร
        "time": "คืนวันเสาร์ เวลา 22:30 น.", // เวลาที่มีนัยสำคัญ (เทศกาล, ครบรอบ, วันพิเศษ) หรือวันทั่วไปก็ได้
        "victim": "คุณสมชาย ธนาคาร",
        "age": "45",
        "cause_of_death": "ถูกวางยาพิษในเครื่องดื่ม",
        "details": "เหยื่อเป็นนักธุรกิจที่มีปฏิปักษ์มากมาย พบเสียชีวิตในห้องสูทของโรงแรม" // รายละเอียดสถานการณ์ที่ดูธรรมดาแต่หากมองดีๆก็จะพบกับความซับซ้อน
    },
    "people": [ 
        // สร้างตัวละคร 4-6 คน (ต้องมีอย่างน้อย 4 คน ไม่ใช่แค่ 2-3 คน) โดยแต่ละคนต้องมีความซับซ้อน
        // **สำคัญมาก: ใช้ชื่อฟิลด์ตามนี้เท่านั้น - ห้ามเปลี่ยนแปลง**
        {
            "name": "คุณปัทมา ธนาคาร",
            "age": "38",
            "role": "ภรรยาของเหยื่อ",
            "relationship": "คู่สมรสที่มีปัญหา",
            "characteristics": "An elegant Thai woman in her late 30s, wearing a sophisticated black evening dress, diamond jewelry, perfectly styled hair in an updo, standing in a luxury hotel lobby, dramatic lighting, professional photography style, high quality, detailed", // คำอธิบายสำหรับสร้างภาพ ต้องเป็นภาษาอังกฤษ
            "secret": "เธอมีชู้กับคนขับรถและวางแผนจะหย่าร้าง แต่กลัวว่าจะไม่ได้มรดก",
            "motive": "ต้องการเงินมรดกและเสรีภาพจากชีวิตแต่งงาน", // แรงจูงใจทางจิตวิทยาที่ลึกซึ้ง
            "alibi": "อยู่ในห้องน้ำผู้หญิงตอนเกิดเหตุ มีสตาฟโรงแรมเห็น", // หลักฐานที่อยู่อาจจะโกหกได้
            "details": "เป็นคนที่ดูสง่างามภายนอก แต่ข้างในมีความโลภและไร้ยางอาย มักจะแสร้งทำเป็นเศร้าโศกเมื่อพูดถึงสามี"
        },
        {
            "name": "คุณรัชนก บุญมี",
            "age": "29",
            "role": "เลขานุการส่วนตัว",
            "relationship": "ผู้ใต้บังคับบัญชาที่ถูกคุกคาม",
            "characteristics": "A professional Thai woman in her late 20s, wearing a conservative business suit, glasses, holding documents, serious expression, office environment background, corporate photography style", // คำอธิบายสำหรับสร้างภาพ ต้องเป็นภาษาอังกฤษ
            "secret": "เธอถูกเหยื่อล่วงละเมิดทางเพศและบังคับให้ทำธุรกิจผิดกฎหมาย",
            "motive": "ต้องการแก้แค้นและหลุดพ้นจากการถูกควบคุม", // แรงจูงใจทางจิตวิทยาที่ลึกซึ้ง
            "alibi": "อยู่ที่โต๊ะแถวหน้า พูดคุยกับแขกเข้าร่วมงาน", // หลักฐานที่อยู่อาจจะโกหกได้
            "details": "ดูเป็นคนเงียบขรึม แต่ข้างในเต็มไปด้วยความโกรธแค้น มักจะหลีกเลี่ยงการสบตากับเหยื่อ"
        },
        // เพิ่มตัวละคร 2-4 คนตามแบบ
    ],
    "evidence": [
        // **สำคัญ: ต้องสร้างหลักฐาน 6-12 ชิ้นครบถ้วน ตามหมวดหมู่ที่กำหนด**
        // **relevance ต้องเป็น: "กายภาพ", "จิตวิทยา", "หลอกลวง", หรือ "เทคโนโลยี" เท่านั้น**
        {
            "type": "แก้วไวน์ที่มีร่องรอยยาพิษ",
            "description": "แก้วไวน์แดงที่พบในห้องของเหยื่อ มีร่องรอยยาพิษไซยาไนด์",
            "location": "โต๊ะข้างเตียงในห้องสูท",
            "relevance": "กายภาพ",
            "image_generation_prompt": "Close-up photo of an elegant wine glass with red wine, sitting on a marble table, dramatic lighting, crime scene photography style, high detail",
            "analysis": "หลักฐานหลักที่พิสูจน์วิธีการฆ่า"
        },
        {
            "type": "จดหมายข่มขู่",
            "description": "จดหมายข่มขู่ลายมือหญิงส่งมา 3 วันก่อน",
            "location": "ในกระเป๋าเอกสารของเหยื่อ",
            "relevance": "หลอกลวง",
            "image_generation_prompt": "Photo of a threatening letter written in Thai, feminine handwriting, on cream paper",
            "analysis": "ลายมือปลอมเพื่อใส่ร้ายภรรยา"
        },
        {
            "type": "ใบเสร็จร้านขายยา",
            "description": "ใบเสร็จซื้อยาขจัดแมลงที่มีส่วนผสมไซยาไนด์ วันที่ซื้อ 2 วันก่อนเกิดเหตุ",
            "location": "ในกระเป๋าถือของเลขานุการ",
            "relevance": "กายภาพ",
            "image_generation_prompt": "Photo of a pharmacy receipt in Thai text, showing pesticide purchase, crumpled paper texture",
            "analysis": "พิสูจน์ว่าเลขานุการซื้อสารพิษ"
        },
        {
            "type": "บันทึกการโทรศัพท์",
            "description": "บันทึกการโทรออกจากมือถือเหยื่อ เวลา 22:00 น. โทรหาภรรยา 3 นาที",
            "location": "ข้อมูลจากผู้ให้บริการโทรศัพท์",
            "relevance": "เทคโนโลยี",
            "image_generation_prompt": "Screenshot of phone call log showing recent calls, mobile phone interface, showing timestamp 22:00, digital evidence style",
            "analysis": "แสดงว่าเหยื่อยังมีชีวิตตอน 22:00 น."
        },
        {
            "type": "ไดอารี่ส่วนตัว",
            "description": "ไดอารี่ของเหยื่อเขียนเมื่อ 1 สัปดาห์ก่อน บันทึกความกลัวและความสงสัย",
            "location": "ลิ้นชักโต๊ะทำงานในบ้าน",
            "relevance": "จิตวิทยา",
            "image_generation_prompt": "Photo of an open diary with handwritten Thai text, personal thoughts, on a wooden desk",
            "analysis": "เผยความรู้สึกของเหยื่อก่อนเสียชีวิต"
        },
        {
            "type": "ลายนิ้วมือบนขวดไวน์",
            "description": "ลายนิ้วมือที่พบบนขวดไวน์ไม่ตรงกับเหยื่อหรือใครในครอบครัว",
            "location": "ขวดไวน์ในห้องครัว",
            "relevance": "กายภาพ",
            "image_generation_prompt": "Close-up forensic photo of fingerprints on wine bottle, crime scene evidence photography",
            "analysis": "ลายนิ้วมือของผู้กระทำผิดที่เหลือไว้"
        },
        {
            "type": "กล้องวงจรปิด",
            "description": "บันทึกภาพจากกล้องลิฟต์ แสดงเลขานุการขึ้นมาชั้น 15 เวลา 21:45 น.",
            "location": "ระบบรักษาความปลอดภัยของโรงแรม",
            "relevance": "เทคโนโลยี",
            "image_generation_prompt": "CCTV footage screenshot showing person in elevator, elevator show floor 15 number, timestamp visible, timestamps show 21:45, security camera style",
            "analysis": "พิสูจน์ว่าเลขานุการอยู่ในโรงแรมก่อนเกิดเหตุ"
        },
        // **ต้องมีหลักฐาน 6-12 ชิ้น ตามที่กำหนด**
    ],
    "resolution": {
        // ต้องมีรายละเอียดครบถ้วนและสมเหตุสมผล รวมถึงการสร้างความประหลาดใจ
        "culprit": "คุณรัชนก บุญมี",
        "description": "แรงจูงใจ: ถูกล่วงละเมิดและบังคับทำธุรกิจผิดกฎหมาย 2 ปี\n\nกลอุบาย: ปลอมลายมือหญิงเขียนจดหมายข่มขู่โยนความผิดให้ภรรยา, ใช้ความรู้เคมีวางยาพิษในไวน์, สร้างข้ออ้างปลอม\n\nขั้นตอนฆาตกรรม: 22:15 น. ใส่ไซยาไนด์ในไวน์ขณะเหยื่ออาบน้ำ วางไว้ตามปกติ เหยื่อตาย 15 นาทีหลังดื่ม\n\nการปกปิดหลักฐาน:ใช้โทรศัพท์ของเหยื่อส่งข้อความจากมือถือเหยื่อ\n\nข้อผิดพลาด: ลืมทำลายใบเสร็จซื้อยาจริง ยังเก็บในกระเป๋า"
    }
}

**หลักการสำคัญ:**
- แต่ละคนต้องมีประวัติที่ซับซ้อน ไม่ใช่แค่คนธรรมดาที่มีแรงจูงใจเดียว
- เหตุการณ์ในอดีตอาจส่งผลต่อการกระทำในปัจจุบัน
- หลักฐานต้องเชื่อมโยงกันและนำไปสู่ความจริง แต่ต้องมีความซับซ้อนและกลอุบาย
- หลักฐานต้องอ้างอิงความรู้ทางวิทยาศาสตร์ที่ถูกต้อง
- หลักฐานหลอกลวงที่ดูน่าเชื่อถือมากและทำให้ผู้เล่นเข้าใจผิด
- แผนการฆาตกรรมต้องแสดงความชาญฉลาดและการวางแผนมานาน
- ทุกคนมีแรงจูงใจเป็นผู้ต้องสงสัย
- **ผู้กระทำผิดดูเป็นผู้ต้องสงสัยน้อยสุด** เพื่อสร้างความประหลาดใจ
- กลอุบายสมเหตุสมผล ชาญฉลาด ซับซ้อน
- ใช้จิตวิทยาหลอกลวง เล่นกับอคติผู้สืบสวน
- ต้องมีการใช้จิตวิทยาในการหลอกลวง เช่น การเล่นกับอคติและความคาดหวังของผู้สืบสวน
- ผู้อ่านต้องประหลาดใจกับตัวฆาตกรและวิธีการ แต่เมื่อทราบแล้วต้องสมเหตุสมผล

**Resolution ต้องมี:** แรงจูงใจลึกซึ้ง, กลอุบายรายละเอียด, การโยนความผิด, ขั้นตอนฆาตกรรม, การปกปิดหลักฐาน, ข้อผิดพลาดร้ายแรง
- แรงจูงใจ: เหตุผลที่ชัดเจนและน่าเชื่อ รวมถึงความสัมพันธ์ที่ซับซ้อนกับเหยื่อ อาจะเป็นแรงจูงใจทางจิตวิทยาที่ลึกซึ้ง
- กลอุบาย: วิธีการฆ่าที่ซับซ้อนและชาญฉลาด เช่น การใช้ยาพิษ, การปลอมแปลงหลักฐาน, การสร้างข้ออ้างที่น่าเชื่อถือ, การใช้เครื่องมือ (ถ้ามี)
- ขั้นตอนฆาตกรรม: เวลาที่แน่นอน, วิธีการฆ่าทีละขั้นตอน, ระยะเวลาที่ใช้ หรือ ลำดับเวลาของเหตุการณ์ที่แท้จริง
- การปกปิดหลักฐาน: หลักฐานปลอม, หลักฐานที่ซ่อน, การทำลายหลักฐาน, การใช้เทคโนโลยีในการปกปิด
- ข้อผิดพลาดร้ายแรง: สิ่งที่ทำให้ผู้กระทำผิดถูกจับได้ แม้จะมีแผนการที่สมบูรณ์แบบ

**สำคัญมาก: ต้องสร้างตัวละคร 4-6 คน และหลักฐาน 6-12 ชิ้นครบถ้วน (ห้ามน้อยกว่า 6 ชิ้น) พร้อมข้อมูลครบทุกฟิลด์**

เช็คให้แน่ใจว่าเมื่อผู้เล่นอ่านหลักฐานและสอบถามตัวละคร พวกเขาจะสามารถรวบรวมข้อมูลและเชื่อมโยงเหตุการณ์ต่างๆ เพื่อค้นหาความจริงได้

**ข้อกำหนดเพิ่มเติมที่สำคัญ:**
- ห้ามเพิ่มข้อความอธิบาย คำกล่าวแนะนำ หรือคำเตือนใดๆ เกี่ยวกับตัวละครที่เป็นบุคคลสมมติ
- ห้ามใส่ข้อความเช่น "(ตัวละครสมมติในบริบทนี้ - ไม่ใช่บุคคลจริง)" หรือคล้ายคลึงกัน
- ใส่เฉพาะข้อมูลที่จำเป็นสำหรับเกมเท่านั้น
- ชื่อตัวละครและเหยื่อให้เป็นชื่อธรรมดาโดยไม่มีข้อความเพิ่มเติมใดๆ

**ข้อกำหนดบังคับ - ไม่ปฏิบัติตามถือว่าไม่ผ่าน:**
1. หลักฐาน (evidence) ต้องมี **อย่างน้อย 6 ชิ้น** ในรูปแบบ Array
2. แต่ละหลักฐานต้องมีฟิลด์ครบ: type, description, location, relevance, image_generation_prompt, analysis  
3. ตัวละคร (people) ต้องมี **4-6 คน**
4. กลอุบาย ต้องมี **3-4 กลวิธี** ใน resolution

**ข้อกำหนดชื่อฟิลด์ตัวละคร - ห้ามใช้ชื่อฟิลด์อื่น:**
- ใช้ "role" ไม่ใช่ "occupation", "job", "work", "position"
- ใช้ "characteristics" ไม่ใช่ "description", "appearance", "looks" และต้องเป็นภาษาอังกฤษเท่านั้น (ห้ามใช้ภาษาไทย)
- ใช้ "details" ไม่ใช่ "personality", "character", "traits"
- ใช้ "relationship" ไม่ใช่ "relation", "connection"
- ต้องมีฟิลด์ครบถ้วน: name, age, role, relationship, characteristics, secret, motive, alibi, details

**ข้อกำหนดฟิลด์หลักฐาน - ห้ามใช้ค่าอื่น:**
- type ต้องเป็นประเภทที่ชัดเจน เช่น "DNA", "จดหมายข่มขู่", "ใบเสร็จ", "บันทึกการโทรศัพท์", "ไดอารี่ส่วนตัว", "ลายนิ้ว", "กล้องวงจรปิด"
- relevance ต้องเป็นหนึ่งในนี้เท่านั้น: "กายภาพ", "จิตวิทยา", "หลอกลวง", "เทคโนโลยี"
- image_generation_prompt ต้องเป็นภาษาอังกฤษเท่านั้น (ห้ามใช้ภาษาไทย)

*RETURN ONLY VALID JSON - NO EXPLANATIONS OR COMMENTS OUTSIDE JSON*"""
    
    # Combine default prompt with extra prompt if provided
    if extra_prompt:
        prompt = default_prompt + "\n\nเพิ่มเติม: " + extra_prompt
    else:
        prompt = default_prompt
    
    max_retries = 8
    for attempt in range(max_retries):
        try:
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
                    except json.JSONDecodeError:
                        # If JSON parsing fails, try to extract JSON from the response
                        import re
                        json_match = re.search(r'\{.*\}', script_text, re.DOTALL)
                        if json_match:
                            script = json.loads(json_match.group())
                        else:
                            raise Exception("Failed to parse generated script as JSON")
                    
                    # Evidence count
                    evidence_count = len(script.get("evidence", []))

                    # Character count
                    character_count = len(script.get("people", []))

                    if character_count < 4 or character_count > 6:
                        raise Exception(f"Invalid character count: {character_count}. Must be between 4 and 6 characters.")
                    if evidence_count < 6:
                        raise Exception(f"Invalid evidence count: {evidence_count}. Must be at least 6 pieces of evidence.")

                    # Validate character field structure
                    required_character_fields = ["name", "age", "role", "relationship", "characteristics", "secret", "motive", "alibi", "details"]
                    forbidden_character_fields = ["occupation", "description", "job", "work", "personality", "character"]
                    
                    for i, person in enumerate(script.get("people", [])):
                        # Check for missing required fields
                        missing_fields = [field for field in required_character_fields if field not in person]
                        if missing_fields:
                            raise Exception(f"Character {i+1} missing required fields: {missing_fields}")
                        
                        # Check for forbidden field names (commonly confused ones)
                        person_fields = set(person.keys())
                        forbidden_found = person_fields.intersection(forbidden_character_fields)
                        if forbidden_found:
                            raise Exception(f"Character {i+1} uses forbidden field names: {list(forbidden_found)}. Use correct field names: role (not occupation), characteristics (not description)")
                        
                        # Validate characteristics is in English
                        characteristics = person.get("characteristics", "")
                        if not characteristics or len(characteristics.strip()) < 20:
                            raise Exception(f"Character {i+1} has invalid characteristics: must be detailed English description for image generation")
                        
                        # Check if characteristics appears to be in Thai (contains Thai characters)
                        thai_chars = any('\u0e00' <= char <= '\u0e7f' for char in characteristics)
                        if thai_chars:
                            raise Exception(f"Character {i+1} characteristics must be in English, not Thai: {characteristics[:50]}...")

                    # Validate evidence field structure  
                    required_evidence_fields = ["type", "description", "location", "relevance", "image_generation_prompt", "analysis"]
                    for i, evidence in enumerate(script.get("evidence", [])):
                        missing_fields = [field for field in required_evidence_fields if field not in evidence]
                        if missing_fields:
                            raise Exception(f"Evidence {i+1} missing required fields: {missing_fields}")
                        
                        # Validate image_generation_prompt is in English
                        prompt_text = evidence.get("image_generation_prompt", "")
                        if not prompt_text or len(prompt_text.strip()) < 10:
                            raise Exception(f"Evidence {i+1} has invalid image_generation_prompt: must be detailed English description")
                        
                        # Check if image_generation_prompt is in Thai (contains Thai characters)
                        thai_chars_in_prompt = any('\u0e00' <= char <= '\u0e7f' for char in prompt_text)
                        if thai_chars_in_prompt:
                            raise Exception(f"Evidence {i+1} image_generation_prompt must be in English, not Thai: {prompt_text[:50]}...")
                        
                        # Validate relevance category
                        relevance = evidence.get("relevance", "")
                        valid_relevance = ["กายภาพ", "จิตวิทยา", "หลอกลวง", "เทคโนโลยี"]
                        if relevance not in valid_relevance:
                            raise Exception(f"Evidence {i+1} has invalid relevance '{relevance}'. Must be one of: {valid_relevance}")

                    # Validate situation structure
                    situation = script.get("situation", {})
                    required_situation_fields = ["location", "time", "victim", "age", "cause_of_death", "details"]
                    missing_situation_fields = [field for field in required_situation_fields if field not in situation]
                    if missing_situation_fields:
                        raise Exception(f"Situation missing required fields: {missing_situation_fields}")

                    # Validate resolution structure
                    resolution = script.get("resolution", {})
                    required_resolution_fields = ["culprit", "description"]
                    missing_resolution_fields = [field for field in required_resolution_fields if field not in resolution]
                    if missing_resolution_fields:
                        raise Exception(f"Resolution missing required fields: {missing_resolution_fields}")
                    
                    # Validate resolution description contains key components
                    resolution_desc = resolution.get("description", "")
                    required_components = ["แรงจูงใจ", "กลอุบาย", "ขั้นตอนฆาตกรรม", "การปกปิดหลักฐาน", "ข้อผิดพลาด"]
                    missing_components = [comp for comp in required_components if comp not in resolution_desc]
                    if missing_components:
                        raise Exception(f"Resolution description missing required components: {missing_components}")

                    # Validate culprit exists in people list
                    culprit_name = resolution.get("culprit", "")
                    character_names = [person.get("name", "") for person in script.get("people", [])]
                    if culprit_name not in character_names:
                        raise Exception(f"Culprit '{culprit_name}' not found in character list: {character_names}")

                    print(f"Script validation passed on attempt {attempt + 1}: {character_count} characters, {evidence_count} evidence pieces")
                    return script
                    
        except Exception as e:
            print(f"Script generation attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                # Last attempt failed, raise the exception
                raise e
            else:
                # Add stronger field name warnings to prompt for retry
                prompt += f"\n\n**CRITICAL ERROR DETECTED - RETRY WITH CORRECT FIELD NAMES:**\nPrevious attempt failed: {str(e)}\nUSE EXACT FIELD NAMES: name, age, role, relationship, characteristics, secret, motive, alibi, details\nDO NOT USE: occupation, description, job, work, personality, character"
                print(f"Retrying script generation with enhanced prompt (attempt {attempt + 2}/{max_retries})")
                continue
                
async def generate_character_images(people: List[Dict], game_id: str):
    """Generate character images using Flux"""
    for i, person in enumerate(people):
        if "characteristics" in person:
            filename = f"{game_id}_character_{i}_{person['name']}"
            print(f"Generating character image: {filename}")
            image_id = await request_image_generation(
                f"{person['characteristics']}, (Portrait Photo), (High Quality, Detailed Background, Sharp Image:1.24), (Hyper-Detailed:1.15), (Photography, Cinematic Photo, Film-Grain:1.2), (Sharp Photo:1.2) (Taken With Canon Eos R5:0.6)",
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
                f"{item['image_generation_prompt']}, (Sharp Photo:1.2) (Taken With A Canon Eos R5:0.6)",
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

ใช้ภาษาไทยที่สุภาพและน่าติดตาม เหมือนการเล่าเรื่องสืบสวนที่สมบูรณ์

**จัดรูปแบบการตอบ:**
- ใช้ **หัวข้อหลัก** ด้วย markdown bold สำหรับแต่ละส่วน
- ขึ้นบรรทัดใหม่ระหว่างส่วนต่างๆ เพื่อความชัดเจน
- ใช้ตัวหนา **ข้อความสำคัญ** เช่น ชื่อผู้กระทำผิด เวลา และวิธีการฆ่า
- ใช้ขีดกลาง (-) สำหรับรายการย่อย
- จัดรูปแบบให้อ่านง่ายและสวยงาม

(ไม่เกิน 400 คำ)"""
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
5. สิ่งที่จะเกิดขึ้นต่อไป (ผลลัพธ์ที่น่าเศร้า):
   - การจับกุมผู้ต้องสงสัยที่ผู้เล่นชี้ แทนผู้กระทำผิดจริง
   - ผู้กระทำผิดจริงหลบหนีไปได้และไม่มีใครรู้ความจริง
   - ผลกระทบต่อผู้ที่ถูกกล่าวหาผิด (เช่น ถูกจับ, ฆ่าตัวตาย, ครอบครัวแตกแยก)
   - ความยุติธรรมไม่เกิดขึ้นและผู้กระทำผิดยังคงเป็นอันตรายต่อสังคม

ใช้ภาษาไทยที่สุภาพแต่เศร้าสลด เล่าเรื่องราวที่สมบูรณ์และน่าเศร้าใจ โดยเน้นผลลัพธ์ที่น่าสลดใจของการทายผิด - ผู้กระทำผิดจริงหลบหนีและคนบริสุทธิ์ต้องแบกรับผลที่ตามมา ใช้โทนเศร้าและให้บทเรียนเกี่ยวกับความสำคัญของการสืบสวนที่ถูกต้อง

**จัดรูปแบบการตอบ:**
- ใช้ **หัวข้อหลัก** ด้วย markdown bold สำหรับแต่ละส่วน
- ขึ้นบรรทัดใหม่ระหว่างส่วนต่างๆ เพื่อความชัดเจน
- ใช้ตัวหนา **ข้อความสำคัญ** เช่น ชื่อผู้กระทำผิด เวลา และผลกระทบ
- ใช้ขีดกลาง (-) สำหรับรายการย่อย
- ใช้ 😢 **โทนเศร้า** สำหรับส่วนผลลัพธ์ที่น่าเศร้า
- จัดรูปแบบให้อ่านง่ายและสร้างอารมณ์    และให้กำลังใจ ใช้ภาषาไทย (ไม่เกิน 400 คำ)"""

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