from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import torch
from diffusers import FluxPipeline
import os
import uuid
from PIL import Image
import asyncio
from typing import Optional

app = FastAPI(title="Flux Image Generation API for Detective Game")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for game services
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global pipeline variable
pipe = None

class ImageRequest(BaseModel):
    prompt: str
    width: Optional[int] = 512
    height: Optional[int] = 512
    num_inference_steps: Optional[int] = 20
    guidance_scale: Optional[float] = 7.5
    filename: Optional[str] = None  # Custom filename for game assets

class ImageResponse(BaseModel):
    image_id: str
    status: str
    message: str
    filename: Optional[str] = None

# Task status tracking
generation_tasks = {}

@app.on_event("startup")
async def load_model():
    """Load the Flux model on startup"""
    global pipe
    try:
        print("Loading Flux model...")
        pipe = FluxPipeline.from_pretrained(
            "black-forest-labs/FLUX.1-dev",  # Using dev model as requested
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None
        )
        if torch.cuda.is_available():
            pipe = pipe.to("cuda")
        print("Flux Dev model loaded successfully!")
    except Exception as e:
        print(f"Error loading model: {e}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "model_loaded": pipe is not None}

@app.post("/generate", response_model=ImageResponse)
async def generate_image(request: ImageRequest, background_tasks: BackgroundTasks):
    """Generate image from prompt"""
    if pipe is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    # Use custom filename or generate UUID
    if request.filename:
        image_id = request.filename
    else:
        image_id = str(uuid.uuid4())
    
    # Initialize task status
    generation_tasks[image_id] = {"status": "processing", "error": None}
    
    # Add background task to generate image
    background_tasks.add_task(
        generate_image_task,
        image_id,
        request.prompt,
        request.width,
        request.height,
        request.num_inference_steps,
        request.guidance_scale
    )
    
    return ImageResponse(
        image_id=image_id,
        status="processing",
        message="Image generation started",
        filename=request.filename
    )

async def generate_image_task(
    image_id: str,
    prompt: str,
    width: int,
    height: int,
    num_inference_steps: int,
    guidance_scale: float
):
    """Background task to generate image"""
    try:
        print(f"Generating image {image_id} with prompt: {prompt[:100]}...")
        
        # Generate image
        with torch.no_grad():
            image = pipe(
                prompt=prompt,
                width=width,
                height=height,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale
            ).images[0]
        
        # Save image
        output_path = f"/app/outputs/{image_id}.png"
        image.save(output_path)
        
        # Update task status
        generation_tasks[image_id] = {"status": "completed", "error": None}
        
        print(f"Image {image_id} generated successfully")
        
    except Exception as e:
        print(f"Error generating image {image_id}: {e}")
        generation_tasks[image_id] = {"status": "failed", "error": str(e)}

@app.get("/image/{image_id}")
async def get_image(image_id: str):
    """Get generated image by ID"""
    image_path = f"/app/outputs/{image_id}.png"
    
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    
    return FileResponse(image_path, media_type="image/png")

@app.get("/status/{image_id}")
async def get_status(image_id: str):
    """Get generation status by ID"""
    if image_id not in generation_tasks:
        # Check if file exists
        image_path = f"/app/outputs/{image_id}.png"
        if os.path.exists(image_path):
            return {"status": "completed", "image_url": f"/image/{image_id}"}
        else:
            return {"status": "not_found"}
    
    task_status = generation_tasks[image_id]
    
    if task_status["status"] == "completed":
        return {
            "status": "completed", 
            "image_url": f"/image/{image_id}",
            "error": None
        }
    elif task_status["status"] == "failed":
        return {
            "status": "failed",
            "error": task_status["error"]
        }
    else:
        return {"status": "processing"}

@app.delete("/clear")
async def clear_images():
    """Clear all generated images (for game restart)"""
    try:
        output_dir = "/app/outputs"
        if os.path.exists(output_dir):
            for filename in os.listdir(output_dir):
                if filename.endswith(".png"):
                    os.remove(os.path.join(output_dir, filename))
        
        # Clear task status
        generation_tasks.clear()
        
        return {"status": "cleared", "message": "All images cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear images: {e}")

@app.get("/list")
async def list_images():
    """List all generated images"""
    try:
        output_dir = "/app/outputs"
        if not os.path.exists(output_dir):
            return {"images": []}
        
        images = []
        for filename in os.listdir(output_dir):
            if filename.endswith(".png"):
                image_id = filename[:-4]  # Remove .png extension
                images.append({
                    "image_id": image_id,
                    "filename": filename,
                    "url": f"/image/{image_id}"
                })
        
        return {"images": images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list images: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)