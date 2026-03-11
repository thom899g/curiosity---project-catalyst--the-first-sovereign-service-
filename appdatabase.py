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