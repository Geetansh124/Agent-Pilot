"""Specialized multi-agent system package."""
from src.agents.coding_agent import CodingAgent, coding_agent, run_code_task
from src.agents.data_agent import DataAnalystAgent, data_analyst_agent, run_data_analysis
from src.agents.research_agent import ResearchAgent, research_agent, run_research
from src.agents.testing_agent import TestingAgent, testing_agent
from src.agents.swarm_coordinator import SwarmCoordinator, swarm_coordinator, SwarmTopology
from src.agents.shared_state import (
    AgentMessage,
    AgentRole,
    InterAgentMessageBus,
    message_bus,
)
from src.agents.supervisor import SupervisorAgent, route_to_specialist, supervisor_agent

__all__ = [
    "AgentRole",
    "AgentMessage",
    "InterAgentMessageBus",
    "message_bus",
    "ResearchAgent",
    "research_agent",
    "run_research",
    "CodingAgent",
    "coding_agent",
    "run_code_task",
    "DataAnalystAgent",
    "data_analyst_agent",
    "run_data_analysis",
    "TestingAgent",
    "testing_agent",
    "SwarmCoordinator",
    "swarm_coordinator",
    "SwarmTopology",
    "SupervisorAgent",
    "supervisor_agent",
    "route_to_specialist",
]

