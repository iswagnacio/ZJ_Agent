"""
Canonical Workplan schema - Pydantic models for validation.

This module defines the authoritative structure for Workplan JSON.
It resolves inconsistencies across the six production examples into
one canonical form that executors can rely on.

Note: This is a simplified schema focusing on core validation.
Full parameter validation is done against models_jsonschema.json.
"""
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field


class ImageInference(BaseModel):
    """Image analysis inference metadata."""
    imageModality: Literal["brightfield", "fluorescence"]
    experimentType: str
    reasoning: List[str]


class Channel(BaseModel):
    """Channel definition."""
    channelId: str
    channelName: str
    semanticRole: str


class Target(BaseModel):
    """Target (ROI) definition."""
    targetName: str
    targetType: str
    description: str


class JobInputs(BaseModel):
    """Common job inputs structure."""
    channelId: Optional[List[str]] = None
    sourceTargetNames: Optional[List[str]] = None
    targetInputs: Optional[List[Dict[str, Any]]] = None
    imageModality: Optional[str] = None
    sourceImageType: Optional[str] = None


class JobOutputs(BaseModel):
    """Common job outputs structure."""
    generatedChannels: Optional[List[str]] = None
    targetName: Optional[str] = None
    resultName: Optional[str] = None


class Job(BaseModel):
    """Base job structure - validation of job-specific plans done separately."""
    jobId: str
    jobName: str
    jobType: Literal["pic_split", "create_target", "formula", "roi_render", "quality_control"]
    stepDescript: str
    inputs: Optional[JobInputs] = None
    outputs: Optional[JobOutputs] = None

    # Job-specific plan fields (validated separately against models_jsonschema.json)
    picSplitPlan: Optional[Dict[str, Any]] = None
    createTargetPlan: Optional[Dict[str, Any]] = None
    formulaPlan: Optional[Dict[str, Any]] = None
    roiRenderPlan: Optional[Dict[str, Any]] = None
    qualityControlPlan: Optional[Dict[str, Any]] = None


class Workplan(BaseModel):
    """
    Canonical Workplan structure.

    This is the single source of truth for workplan validation.
    Executors should consume this schema.
    """
    experimentName: str
    inputMode: str
    analysisGoal: str
    imageInference: ImageInference
    workplanSceneType: str
    channels: List[Channel]
    targets: List[Target]
    jobs: List[Job]

    class Config:
        extra = "allow"  # Allow additional fields for forward compatibility
