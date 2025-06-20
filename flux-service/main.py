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
from typing import Optional, List
from huggingface_hub import login

app = FastAPI(
    title="Flux Image Generation Service",
    description="AI-powered image generation service for the niti detective game using Flux diffusion models",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

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

# Environment variables for Hugging Face configuration
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL_REPO = os.getenv("HF_MODEL_REPO", "black-forest-labs/FLUX.1-dev")
HF_CACHE_DIR = os.getenv("HF_CACHE_DIR", "/app/models")

class ImageRequest(BaseModel):
    """Request model for image generation"""
    prompt: str
    width: Optional[int] = 512
    height: Optional[int] = 512
    num_inference_steps: Optional[int] = 20
    guidance_scale: Optional[float] = 7.5
    filename: Optional[str] = None  # Custom filename for game assets

class ImageResponse(BaseModel):
    """Response model for image generation request"""
    image_id: str
    status: str
    message: str
    filename: Optional[str] = None

class StatusResponse(BaseModel):
    """Response model for generation status"""
    status: str
    image_url: Optional[str] = None
    error: Optional[str] = None

class ImageListItem(BaseModel):
    """Individual image item in list response"""
    image_id: str
    filename: str
    url: str

class ImageListResponse(BaseModel):
    """Response model for image list"""
    images: List[ImageListItem]

class ClearResponse(BaseModel):
    """Response model for clear operation"""
    status: str
    message: str

class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str
    model_loaded: bool
    service: str
    version: str
    gpu_available: bool

class ModelResponse(BaseModel):
    """Response model for model operations"""
    status: str
    message: str
    model_loaded: bool

# Task status tracking
generation_tasks = {}

@app.on_event("startup")
async def load_model():
    """Load the Flux model on startup"""
    global pipe
    try:
        # Login to Hugging Face if token is provided
        if HF_TOKEN:
            print("Logging in to Hugging Face...")
            login(token=HF_TOKEN)
            print("Hugging Face login successful!")
        else:
            print("Warning: No HF_TOKEN provided. Some models may not be accessible.")
        
        print(f"Loading Flux model from {HF_MODEL_REPO}...")
        pipe = FluxPipeline.from_pretrained(
            HF_MODEL_REPO,
            torch_dtype=torch.bfloat16,
            cache_dir=HF_CACHE_DIR
        )

        # Save some VRAM by offloading the model to CPU
        if torch.cuda.is_available():
            pipe.enable_model_cpu_offload()
        print(f"Flux model ({HF_MODEL_REPO}) loaded successfully!")
    except Exception as e:
        print(f"Error loading model: {e}")
        if "access" in str(e).lower() or "gated" in str(e).lower():
            print("This might be due to missing or invalid HF_TOKEN for gated models.")
            print("Please check your Hugging Face token and model access permissions.")

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint
    
    Returns the current health status of the Flux image generation service,
    including model loading status and GPU availability.
    """
    return HealthResponse(
        status="healthy",
        model_loaded=pipe is not None,
        service="flux-service",
        version="1.0.0",
        gpu_available=torch.cuda.is_available()
    )

@app.post("/generate", response_model=ImageResponse, tags=["Image Generation"])
async def generate_image(request: ImageRequest, background_tasks: BackgroundTasks):
    """
    Generate image from text prompt
    
    Creates AI-generated images using the Flux diffusion model.
    Perfect for generating character portraits and evidence images
    for the detective game.
    
    Parameters:
    - **prompt**: Text description of the image to generate
    - **width**: Image width in pixels (default: 512)
    - **height**: Image height in pixels (default: 512)
    - **num_inference_steps**: Number of denoising steps (default: 20)
    - **guidance_scale**: How closely to follow the prompt (default: 7.5)
    - **filename**: Custom filename for the generated image (optional)
    """
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

@app.get("/image/{image_id}", tags=["Image Retrieval"])
async def get_image(image_id: str):
    """
    Get generated image by ID
    
    Returns the actual image file for the given image ID.
    Used to retrieve character portraits, evidence images,
    and other generated assets for the detective game.
    """
    image_path = f"/app/outputs/{image_id}.png"
    
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    
    return FileResponse(image_path, media_type="image/png")

@app.get("/status/{image_id}", response_model=StatusResponse, tags=["Image Generation"])
async def get_status(image_id: str):
    """
    Get generation status by image ID
    
    Check the current status of an image generation task.
    Returns one of: processing, completed, failed, or not_found.
    For completed images, includes the URL to retrieve the image.
    """
    if image_id not in generation_tasks:
        # Check if file exists
        image_path = f"/app/outputs/{image_id}.png"
        if os.path.exists(image_path):
            return StatusResponse(status="completed", image_url=f"/image/{image_id}")
        else:
            return StatusResponse(status="not_found")
    
    task_status = generation_tasks[image_id]
    
    if task_status["status"] == "completed":
        return StatusResponse(
            status="completed", 
            image_url=f"/image/{image_id}",
            error=None
        )
    elif task_status["status"] == "failed":
        return StatusResponse(
            status="failed",
            error=task_status["error"]
        )
    else:
        return StatusResponse(status="processing")

@app.delete("/clear", response_model=ClearResponse, tags=["Image Management"])
async def clear_images():
    """
    Clear all generated images
    
    Removes all generated images from storage and clears
    the generation task status. Used when restarting
    the detective game or cleaning up storage.
    """
    try:
        output_dir = "/app/outputs"
        if os.path.exists(output_dir):
            for filename in os.listdir(output_dir):
                if filename.endswith(".png"):
                    os.remove(os.path.join(output_dir, filename))
        
        # Clear task status
        generation_tasks.clear()
        
        return ClearResponse(status="cleared", message="All images cleared")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear images: {e}")

@app.get("/list", response_model=ImageListResponse, tags=["Image Management"])
async def list_images():
    """
    List all generated images
    
    Returns a list of all currently stored images
    with their IDs, filenames, and URLs for retrieval.
    Useful for debugging and asset management.
    """
    try:
        output_dir = "/app/outputs"
        if not os.path.exists(output_dir):
            return ImageListResponse(images=[])
        
        images = []
        for filename in os.listdir(output_dir):
            if filename.endswith(".png"):
                image_id = filename[:-4]  # Remove .png extension
                images.append(ImageListItem(
                    image_id=image_id,
                    filename=filename,
                    url=f"/image/{image_id}"
                ))
        
        return ImageListResponse(images=images)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list images: {e}")

@app.post("/unload", response_model=ModelResponse, tags=["Model Management"])
async def unload_model():
    """
    Unload the Flux model from memory
    
    Removes the Flux model from GPU/CPU memory to free up resources.
    This is useful after all image generation tasks are completed
    to reduce memory usage. The model can be reloaded later if needed.
    """
    global pipe
    try:
        if pipe is not None:
            # Move model to CPU first if it was on GPU
            if torch.cuda.is_available() and next(pipe.unet.parameters()).is_cuda:
                pipe = pipe.to("cpu")
            
            # Clear CUDA cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            # Delete the pipeline
            del pipe
            pipe = None
            
            # Force garbage collection
            import gc
            gc.collect()
            
            # Additional CUDA cleanup
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            
            return ModelResponse(
                status="success",
                message="Model unloaded successfully, memory freed",
                model_loaded=False
            )
        else:
            return ModelResponse(
                status="info",
                message="Model was not loaded",
                model_loaded=False
            )
    except Exception as e:
        return ModelResponse(
            status="error",
            message=f"Failed to unload model: {e}",
            model_loaded=pipe is not None
        )

@app.post("/reload", response_model=ModelResponse, tags=["Model Management"])
async def reload_model():
    """
    Reload the Flux model into memory
    
    Loads the Flux model back into GPU/CPU memory after it has been unloaded.
    This allows the service to resume image generation capabilities.
    """
    global pipe
    try:
        if pipe is not None:
            return ModelResponse(
                status="info",
                message="Model is already loaded",
                model_loaded=True
            )
        
        # Login to Hugging Face if token is provided
        if HF_TOKEN:
            login(token=HF_TOKEN)
        
        print(f"Reloading Flux model from {HF_MODEL_REPO}...")
        pipe = FluxPipeline.from_pretrained(
            HF_MODEL_REPO,
            torch_dtype=torch.bfloat16,
            cache_dir=HF_CACHE_DIR
        )

        # Save some VRAM by offloading the model to CPU
        if torch.cuda.is_available():
            pipe.enable_model_cpu_offload()
        
        return ModelResponse(
            status="success",
            message="Model reloaded successfully",
            model_loaded=True
        )
    except Exception as e:
        return ModelResponse(
            status="error",
            message=f"Failed to reload model: {e}",
            model_loaded=False
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)