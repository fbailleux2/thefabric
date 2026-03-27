from __future__ import annotations

import json
from typing import Any, Dict, List

from ..models import DailySession


def build_pyspur_workflow(session: DailySession, analysis: Dict[str, Any]) -> Dict[str, Any]:
    input_schema = {
        "session_summary": "string",
        "process_context": "string",
        "observed_steps": "array",
        "decisions": "array",
        "irritants": "array",
        "documents_needed": "array",
        "bundle_candidates": "array",
    }
    input_json_schema = _json_schema(
        {
            "session_summary": {"type": "string"},
            "process_context": {"type": "string"},
            "observed_steps": {"type": "array"},
            "decisions": {"type": "array"},
            "irritants": {"type": "array"},
            "documents_needed": {"type": "array"},
            "bundle_candidates": {"type": "array"},
        },
        required=list(input_schema.keys()),
    )

    planner_output_schema = {
        "workflow_summary": "string",
        "automation_plan": "string",
        "knowledge_requirements": "string",
        "bundle_strategy": "string",
    }
    planner_output_json = _json_schema(
        {
            "workflow_summary": {"type": "string"},
            "automation_plan": {"type": "string"},
            "knowledge_requirements": {"type": "string"},
            "bundle_strategy": {"type": "string"},
        },
        required=list(planner_output_schema.keys()),
    )

    delivery_output_schema = {
        "operator_brief": "string",
        "hermes_handoff": "string",
        "risk_controls": "string",
    }
    delivery_output_json = _json_schema(
        {
            "operator_brief": {"type": "string"},
            "hermes_handoff": {"type": "string"},
            "risk_controls": {"type": "string"},
        },
        required=list(delivery_output_schema.keys()),
    )

    nodes: List[Dict[str, Any]] = [
        {
            "id": "input_node",
            "title": "input_node",
            "parent_id": None,
            "node_type": "InputNode",
            "config": {
                "output_schema": input_schema,
                "output_json_schema": input_json_schema,
                "has_fixed_output": False,
                "enforce_schema": False,
            },
            "coordinates": {"x": 0, "y": 220},
        },
        {
            "id": "WorkflowPlanner",
            "title": "WorkflowPlanner",
            "parent_id": None,
            "node_type": "SingleLLMCallNode",
            "config": {
                "title": "WorkflowPlanner",
                "type": "object",
                "output_schema": planner_output_schema,
                "output_json_schema": planner_output_json,
                "has_fixed_output": False,
                "llm_info": {
                    "model": "openai/chatgpt-4o-latest",
                    "max_tokens": 4096,
                    "temperature": 0.2,
                    "top_p": 0.9,
                },
                "system_message": (
                    "You are TheFabric inside PySpur. Transform a machine-readable daily work "
                    "session into an automation workflow. Identify the repeatable steps, the "
                    "decision points that need Hermes memory, and the knowledge gaps that must "
                    "be covered by KFabric. Return concise but structured content."
                ),
                "user_message": (
                    "Process context: {{input_node.process_context}}\n"
                    "Session summary: {{input_node.session_summary}}\n"
                    "Observed steps: {{input_node.observed_steps}}\n"
                    "Decision points: {{input_node.decisions}}\n"
                    "Irritants: {{input_node.irritants}}\n"
                    "Documents needed: {{input_node.documents_needed}}\n"
                    "Known bundle candidates: {{input_node.bundle_candidates}}"
                ),
                "few_shot_examples": None,
                "url_variables": None,
            },
            "coordinates": {"x": 430, "y": 100},
        },
        {
            "id": "AutomationBriefWriter",
            "title": "AutomationBriefWriter",
            "parent_id": None,
            "node_type": "SingleLLMCallNode",
            "config": {
                "title": "AutomationBriefWriter",
                "type": "object",
                "output_schema": delivery_output_schema,
                "output_json_schema": delivery_output_json,
                "has_fixed_output": False,
                "llm_info": {
                    "model": "openai/chatgpt-4o-latest",
                    "max_tokens": 4096,
                    "temperature": 0.3,
                    "top_p": 0.9,
                },
                "system_message": (
                    "You write the final operator brief for a hybrid system where PySpur "
                    "defines the workflow and Hermes executes and learns. Produce a handoff "
                    "ready for automation implementation."
                ),
                "user_message": (
                    "Workflow summary: {{WorkflowPlanner.workflow_summary}}\n"
                    "Automation plan: {{WorkflowPlanner.automation_plan}}\n"
                    "Knowledge requirements: {{WorkflowPlanner.knowledge_requirements}}\n"
                    "Bundle strategy: {{WorkflowPlanner.bundle_strategy}}"
                ),
                "few_shot_examples": None,
                "url_variables": None,
            },
            "coordinates": {"x": 930, "y": 100},
        },
    ]

    links = [
        {"source_id": "input_node", "target_id": "WorkflowPlanner"},
        {"source_id": "WorkflowPlanner", "target_id": "AutomationBriefWriter"},
    ]

    test_inputs = [
        {
            "id": session.session_id,
            "session_summary": analysis["summary"],
            "process_context": analysis["process_context"],
            "observed_steps": [step["label"] for step in analysis["observed_steps"]],
            "decisions": [decision["question"] for decision in analysis["decisions"]],
            "irritants": [irritant["title"] for irritant in analysis["irritants"]],
            "documents_needed": analysis["documents_needed"],
            "bundle_candidates": [],
        }
    ]

    return {
        "name": "TheFabric Workflow - {0}".format(session.process_context.replace("-", " ").title()),
        "metadata": {
            "name": "TheFabric Workflow",
            "description": "Workflow PySpur genere depuis une session quotidienne analysee par TheFabric.",
            "features": [
                "Session analysis ingestion",
                "Hermes handoff design",
                "Bundle-aware automation planning",
                "KFabric knowledge requirements",
            ],
        },
        "definition": {
            "nodes": nodes,
            "links": links,
            "test_inputs": test_inputs,
        },
        "description": analysis["summary"],
    }


def _json_schema(properties: Dict[str, Dict[str, str]], required: List[str]) -> str:
    return json.dumps(
        {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        indent=2,
    )
