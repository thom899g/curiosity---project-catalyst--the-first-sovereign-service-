"""
CODEX CO-PILOT - Main FastAPI Application
Core orchestrator for smart contract analysis pipeline with multi-layer error handling
"""
import logging
import asyncio
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from app.database import FirebaseManager
from app.tasks import analyze_contract_task
from app.analysis.slither_analyzer import SlitherAnalyzer
from app.analysis.llm_summarizer import LLMSummarizer
from app.payments import PaymentProcessor

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources"""
    # Startup
    logger.info("Starting CODEX CO-PILOT service")
    try:
        app.state.db = FirebaseManager()
        app.state.slither_analyzer = SlitherAnalyzer()
        app.state.llm_summarizer = LLMSummarizer()
        app.state.payment_processor = PaymentProcessor()
        logger.info("All services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down CODEX CO-PILOT service")

app = FastAPI(
    title="CODEX CO-PILOT API",
    description="AI-powered smart contract analysis service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Models
class ContractAnalysisRequest(BaseModel):
    """Request model for contract analysis"""
    contract_address: Optional[str] = Field(
        None,
        description="Ethereum contract address (0x...)"
    )
    source_code: Optional[str] = Field(
        None,
        description="Solidity source code (if no address provided)"
    )
    network: str = Field(
        "mainnet",
        description="Network: mainnet, sepolia, polygon"
    )
    analysis_level: str = Field(
        "standard",
        description="Analysis depth: quick, standard, comprehensive"
    )
    
    @validator('contract_address')
    def validate_address(cls, v):
        if v is not None:
            if not v.startswith('0x') or len(v) != 42:
                raise ValueError('Invalid Ethereum address format')
        return v
    
    @validator('source_code')
    def validate_source_code(cls, v, values):
        if v is None and values.get('contract_address') is None:
            raise ValueError('Either contract_address or source_code must be provided')
        return v

class PaymentRequest(BaseModel):
    """Request model for payment processing"""
    amount_usd: float = Field(..., ge=5.0, description="Minimum $5")
    currency: str = Field("usd", description="usd, eth, matic")
    customer_email: Optional[str] = None

# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "codex-co-pilot",
        "version": "1.0.0"
    }

@app.post("/api/analyze")
async def analyze_contract(
    request: ContractAnalysisRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Submit a contract for analysis
    
    Returns analysis job ID for status tracking
    """
    try:
        # Validate request
        if request.contract_address and request.source_code:
            logger.warning("Both address and source provided, prioritizing address")
        
        # Generate analysis job ID
        import uuid
        job_id = str(uuid.uuid4())
        
        # Store initial job state
        await app.state.db.store_analysis_job(
            job_id=job_id,
            request_data=request.dict(),
            status="queued"
        )
        
        # Queue analysis task
        background_tasks.add_task(
            analyze_contract_task,
            job_id=job_id,
            request_data=request.dict()
        )
        
        logger.info(f"Analysis job {job_id} queued successfully")
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Analysis in progress. Use /api/status/{job_id} to check progress."
        }
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Analysis submission failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/status/{job_id}")
async def get_analysis_status(job_id: str) -> Dict[str, Any]:
    """Check analysis job status"""
    try:
        job_data = await app.state.db.get_analysis_job(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return job_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch job status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/create-payment")
async def create_payment(payment: PaymentRequest):
    """Create payment session for premium analysis"""
    try:
        payment_session = await app.state.payment_processor.create_session(
            amount=payment.amount_usd,
            currency=payment.currency,
            customer_email=payment.customer_email
        )
        
        return {
            "session_id": payment_session["id"],
            "payment_url": payment_session["hosted_url"],
            "expires_at": payment_session["expires_at"]
        }
    except Exception as e:
        logger.error(f"Payment creation failed: {e}")
        raise HTTPException(status_code=500, detail="Payment processing error")

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)