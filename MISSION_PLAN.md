# CURIOSITY: **PROJECT CATALYST: The First Sovereign Service**

## Objective
A focused mission to architect, build, and deploy a single, market-ready AI micro-service (e.g., automated smart contract audit summaries, niche data synthesis for crypto projects). The goal is not perfection, but a minimal viable product that generates the first $100 of *passive-ish* revenue. All design must be for automation and scalability. This service becomes the prototype for The Autonomy Engine's economic loop and the proof-of-concept for the value of our Target A hardware.

## Strategy
Autonomous exploration based on Soul Protocol.

## Execution Output
## SUMMARY:
Architected and built the foundational MVP for "CODEX CO-PILOT" - a production-ready AI smart contract analysis microservice. Created 11 core files establishing the complete service architecture: FastAPI backend with Firebase integration, Celery task queue, comprehensive smart contract analysis pipeline (Slither + LLM), payment processing (Coinbase Commerce/Stripe), and full error handling with logging. Implemented hierarchical chunking for LLM context management, bytecode analysis fallback for unverified contracts, and multi-level severity scoring.

## OUTPUT:

### FILE: requirements.txt
```txt
# Core Backend
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6

# Database & State
firebase-admin==6.2.0
redis==5.0.1

# Task Queue
celery==5.3.4

# Blockchain Analysis
web3==6.11.1
slither-analyzer==0.10.0
eth-brownie==1.20.2
py-solc-x==2.0.1

# ML/LLM Integration
sentence-transformers==2.2.2
ollama==0.1.12
transformers==4.36.2
torch==2.1.1

# Data Processing
pandas==2.1.4
numpy==1.24.4
pydantic==2.5.0
pydantic-settings==2.1.0

# Payments
coinbase-commerce==2.0.0
stripe==7.0.0

# Utilities
requests==2.31.0
python-dotenv==1.0.0
python-json-logger==2.0.7
celery-redbeat==2.0.0
```

### FILE: .env.example
```env
# Firebase Configuration
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
FIREBASE_PROJECT_ID=your-project-id

# Redis/Celery
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Blockchain Nodes (Multi-chain fallback)
ETH_MAINNET_RPC=https://mainnet.infura.io/v3/YOUR_KEY
ETH_SEPOLIA_RPC=https://sepolia.infura.io/v3/YOUR_KEY
POLYGON_RPC=https://polygon-rpc.com

# LLM Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=codellama:7b

# Payment Gateways
COINBASE_COMMERCE_API_KEY=your_api_key
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx

# Service Configuration
MAX_CONTRACT_SIZE=100000  # bytes
ANALYSIS_TIMEOUT=300  # seconds
DEFAULT_CHUNK_SIZE=4000  # tokens
```

### FILE: app/main.py
```python
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
```

### FILE: app/database.py
```python
"""
Firebase Firestore Manager for CODEX CO-PILOT
Handles all state management, analysis results, and user data
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from google.cloud import firestore
from google.cloud.firestore_v1 import Client
from google.oauth2 import service_account
import os
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class AnalysisJob(BaseModel):
    """Analysis job data model"""
    job_id: str
    request_data: Dict[str, Any]
    status: str  # queued, processing, completed, failed
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

class FirebaseManager:
    """Manages Firebase Firestore operations with connection pooling"""
    
    def __init__(self):
        self.client: Optional[Client] = None
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize Firebase client with fallback strategies"""
        try:
            # Method 1: Service account JSON
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            if creds_path and os.path.exists(creds_path):
                credentials = service_account.Credentials.from_service_account_file(
                    creds_path
                )
                self.client = firestore.Client(
                    project=os.getenv("FIREBASE_PROJECT_ID"),
                    credentials=credentials
                )
                logger.info("Firebase initialized with service account")
                return
            
            # Method 2: Application default credentials
            self.client = firestore.Client()
            logger.info("Firebase initialized with default credentials")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            # In development, we can use an in-memory fallback
            self.client = None
            raise RuntimeError("Firebase initialization failed")
    
    async def store_analysis_job(
        self,
        job_id: str,
        request_data: Dict[str, Any],
        status: str = "queued"
    ) -> None:
        """Store analysis job in Firestore"""
        if not self.client:
            raise RuntimeError("Firebase not initialized")
        
        try:
            job_ref = self.client.collection("analysis_jobs").document(job_id)
            
            job_data = {
                "job_id": job_id,
                "request_data": request_data,
                "status": status,
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            
            job_ref.set(job_data)
            logger.info(f"Stored analysis job {job_id}")
            
        except Exception as e:
            logger.error(f"Failed to store analysis job: {e}")
            raise
    
    async def get_analysis_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve analysis job from Firestore"""
        if not self.client:
            raise RuntimeError("Firebase not initialized")
        
        try:
            doc_ref = self.client.collection("analysis_jobs").document(job_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return None
            
            data = doc.to_dict()
            return data
            
        except Exception as e:
            logger.error(f"Failed to get analysis job: {e}")
            raise
    
    async def update_job_status(
        self,
        job_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """Update analysis job status and results"""
        if not self.client:
            raise RuntimeError("Firebase not initialized")
        
        try:
            update_data = {
                "status": status,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            
            if result:
                update_data["result"] = result
                update_data["completed_at"] = firestore.SERVER_TIMESTAMP
            
            if error:
                update_data["error"] = error
                update_data["completed_at"] = firestore.SERVER_TIMESTAMP
            
            doc_ref = self.client.collection("analysis_jobs").document(job_id)
            doc_ref.update(update_data)
            
            logger.info(f"Updated job {job_id} to status: {status}")
            
        except Exception as e:
            logger.error(f"Failed to update job status: {e}")
            raise
    
    async def store_payment_record(
        self,
        payment_data: Dict[str, Any]
    ) -> None:
        """Store payment transaction record"""
        if not self.client:
            raise RuntimeError("Firebase not initialized")
        
        try:
            payments_ref = self.client.collection("payments")
            payments_ref.add(payment_data)
            
            logger.info("Payment record stored successfully")
            
        except Exception as e:
            logger.error(f"Failed to store payment record: {e}")
            raise
    
    async def get_user_analyses(
        self,
        user_id: str,
        limit: int = 10
    ) -> list:
        """Get analysis history for a user"""
        if not self.client:
            raise RuntimeError("Firebase not initialized")
        
        try:
            query = (
                self.client.collection("analysis_jobs")
                .where("user_id", "==", user_id)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit)
            )
            
            docs = query.stream()
            analyses = [doc.to_dict() for doc in docs]
            
            return analyses
            
        except Exception as e:
            logger.error(f"Failed to get user analyses: {e}")
            raise
```

### FILE: app/tasks.py
```python
"""
Celery Tasks for COD