"""
Smart Academic Assessment System - API v1 Router Aggregator
"""

from fastapi import APIRouter
try:
    from app.v1.endpoints import audit, health, courses, register, advising, students, lab
except ImportError:
    from backend.app.v1.endpoints import audit, health, courses, register, advising, students, lab

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(audit.router)
api_router.include_router(courses.router)
api_router.include_router(register.router)
api_router.include_router(advising.router)
api_router.include_router(students.router)
api_router.include_router(lab.router)
