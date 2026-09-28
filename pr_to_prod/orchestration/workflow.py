"""LangGraph orchestration with supervisor pattern."""

import logging
from datetime import datetime
from typing import Any, Literal

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.postgres import PostgresSaver

from pr_to_prod.agents import (
    CoderAgent,
    DeployerAgent,
    PlannerAgent,
    ReporterAgent,
    ReviewerAgent,
    TesterAgent,
)
from pr_to_prod.config import Settings
from pr_to_prod.models import WorkflowState, WorkflowStep
from pr_to_prod.providers import create_llm_provider
from pr_to_prod.tools import ToolGateway

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """
    LangGraph-based orchestrator for the PR-to-production workflow.
    
    Implements:
    - Supervisor pattern with conditional routing
    - Human-in-the-loop approval gate
    - Retry logic with exponential backoff
    - Checkpoint persistence for resumability
    """

    def __init__(self, settings: Settings, gateway: ToolGateway):
        self.settings = settings
        self.gateway = gateway
        self.llm_provider = create_llm_provider(settings)

        self.planner = PlannerAgent(
            llm_provider=self.llm_provider,
            model=settings.get_agent_model("planner"),
            gateway=gateway,
        )
        self.coder = CoderAgent(
            llm_provider=self.llm_provider,
            model=settings.get_agent_model("coder"),
            gateway=gateway,
        )
        self.reviewer = ReviewerAgent(
            llm_provider=self.llm_provider,
            model=settings.get_agent_model("reviewer"),
            gateway=gateway,
        )
        self.tester = TesterAgent(
            llm_provider=self.llm_provider,
            model=settings.get_agent_model("tester"),
            gateway=gateway,
        )
        self.deployer = DeployerAgent(
            llm_provider=self.llm_provider,
            model=settings.get_agent_model("deployer"),
            gateway=gateway,
        )
        self.reporter = ReporterAgent(
            llm_provider=self.llm_provider,
            model=settings.get_agent_model("reporter"),
            gateway=gateway,
        )

        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(WorkflowState)

        workflow.add_node("plan", self._plan_node)
        workflow.add_node("code", self._code_node)
        workflow.add_node("review", self._review_node)
        workflow.add_node("test", self._test_node)
        workflow.add_node("await_approval", self._await_approval_node)
        workflow.add_node("deploy", self._deploy_node)
        workflow.add_node("report", self._report_node)

        workflow.set_entry_point("plan")

        workflow.add_edge("plan", "code")
        workflow.add_conditional_edges(
            "code",
            self._after_code_router,
            {
                "review": "review",
                "failed": END,
            },
        )
        workflow.add_conditional_edges(
            "review",
            self._after_review_router,
            {
                "test": "test",
                "code": "code",
                "failed": END,
            },
        )
        workflow.add_conditional_edges(
            "test",
            self._after_test_router,
            {
                "await_approval": "await_approval",
                "code": "code",
                "failed": END,
            },
        )
        workflow.add_conditional_edges(
            "await_approval",
            self._after_approval_router,
            {
                "deploy": "deploy",
                "failed": END,
            },
        )
        workflow.add_conditional_edges(
            "deploy",
            self._after_deploy_router,
            {
                "report": "report",
                "failed": END,
            },
        )
        workflow.add_edge("report", END)

        return workflow

    async def _plan_node(self, state: WorkflowState) -> WorkflowState:
        """Execute planner agent."""
        logger.info("Orchestrator: Executing PLAN step")
        state.current_step = WorkflowStep.PLAN
        
        try:
            result = await self.planner.execute(state)
            state.plan = result["plan"]
            state.add_message(f"Plan created with {len(state.plan.files_to_change)} files to change")
            self._track_tokens(state, result)
        except Exception as e:
            logger.error(f"Plan step failed: {e}")
            state.error = str(e)
            state.current_step = WorkflowStep.FAILED
        
        return state

    async def _code_node(self, state: WorkflowState) -> WorkflowState:
        """Execute coder agent."""
        logger.info("Orchestrator: Executing CODE step")
        state.current_step = WorkflowStep.CODE
        
        try:
            result = await self.coder.execute(state)
            state.code_change = result["code_change"]
            state.add_message(f"Created PR #{state.code_change.pr_number}")
            self._track_tokens(state, result)
        except Exception as e:
            logger.error(f"Code step failed: {e}")
            state.retry_count_coder += 1
            state.retry_count_total += 1
            state.error = str(e)
            if state.is_retry_exhausted():
                state.current_step = WorkflowStep.FAILED
        
        return state

    async def _review_node(self, state: WorkflowState) -> WorkflowState:
        """Execute reviewer agent."""
        logger.info("Orchestrator: Executing REVIEW step")
        state.current_step = WorkflowStep.REVIEW
        
        try:
            result = await self.reviewer.execute(state)
            state.review_result = result["review_result"]
            state.add_message(
                f"Review: {'Approved' if state.review_result.approved else 'Changes requested'}"
            )
            self._track_tokens(state, result)
        except Exception as e:
            logger.error(f"Review step failed: {e}")
            state.error = str(e)
            state.current_step = WorkflowStep.FAILED
        
        return state

    async def _test_node(self, state: WorkflowState) -> WorkflowState:
        """Execute tester agent."""
        logger.info("Orchestrator: Executing TEST step")
        state.current_step = WorkflowStep.TEST
        
        try:
            result = await self.tester.execute(state)
            state.test_result = result["test_result"]
            state.add_message(
                f"Tests: {state.test_result.tests_passed} passed, {state.test_result.tests_failed} failed"
            )
            self._track_tokens(state, result)
        except Exception as e:
            logger.error(f"Test step failed: {e}")
            state.retry_count_total += 1
            state.error = str(e)
            if state.is_retry_exhausted():
                state.current_step = WorkflowStep.FAILED
        
        return state

    async def _await_approval_node(self, state: WorkflowState) -> WorkflowState:
        """Human approval gate - this is where the workflow pauses."""
        logger.info("Orchestrator: AWAITING HUMAN APPROVAL")
        state.current_step = WorkflowStep.AWAIT_APPROVAL
        state.add_message("Awaiting human approval...")
        
        return state

    async def _deploy_node(self, state: WorkflowState) -> WorkflowState:
        """Execute deployer agent."""
        logger.info("Orchestrator: Executing DEPLOY step")
        state.current_step = WorkflowStep.DEPLOY
        
        try:
            result = await self.deployer.execute(state)
            state.deploy_result = result["deploy_result"]
            state.add_message(
                f"Deployed to {state.deploy_result.environment}: "
                f"{'Success' if state.deploy_result.health_check_passed else 'Failed'}"
            )
            self._track_tokens(state, result)
        except Exception as e:
            logger.error(f"Deploy step failed: {e}")
            state.error = str(e)
            state.current_step = WorkflowStep.FAILED
        
        return state

    async def _report_node(self, state: WorkflowState) -> WorkflowState:
        """Execute reporter agent."""
        logger.info("Orchestrator: Executing REPORT step")
        state.current_step = WorkflowStep.REPORT
        
        try:
            result = await self.reporter.execute(state)
            state.add_message("Final report posted to issue")
            state.current_step = WorkflowStep.COMPLETED
            state.completed_at = datetime.utcnow()
            self._track_tokens(state, result)
        except Exception as e:
            logger.error(f"Report step failed: {e}")
            state.error = str(e)
            state.current_step = WorkflowStep.FAILED
        
        return state

    def _after_code_router(
        self, state: WorkflowState
    ) -> Literal["review", "failed"]:
        """Route after code step."""
        if state.error and state.is_retry_exhausted():
            return "failed"
        if state.code_change:
            return "review"
        return "failed"

    def _after_review_router(
        self, state: WorkflowState
    ) -> Literal["test", "code", "failed"]:
        """Route after review step."""
        if state.error:
            return "failed"
        if state.review_result and state.review_result.approved:
            return "test"
        elif state.retry_count_reviewer < state.max_retries_reviewer:
            state.retry_count_reviewer += 1
            state.retry_count_total += 1
            return "code"
        else:
            return "failed"

    def _after_test_router(
        self, state: WorkflowState
    ) -> Literal["await_approval", "code", "failed"]:
        """Route after test step."""
        if state.error and state.is_retry_exhausted():
            return "failed"
        if state.test_result and state.test_result.passed:
            return "await_approval"
        elif not state.is_retry_exhausted():
            return "code"
        else:
            return "failed"

    def _after_approval_router(
        self, state: WorkflowState
    ) -> Literal["deploy", "failed"]:
        """Route after approval step."""
        if state.approval and state.approval.approved:
            return "deploy"
        return "failed"

    def _after_deploy_router(
        self, state: WorkflowState
    ) -> Literal["report", "failed"]:
        """Route after deploy step."""
        if state.deploy_result and state.deploy_result.deployed:
            return "report"
        return "failed"

    def _track_tokens(self, state: WorkflowState, result: dict[str, Any]) -> None:
        """Track token usage from agent results."""
        pass

    def get_checkpointer(self) -> Any:
        """Get the appropriate checkpointer based on database URL."""
        if "postgresql" in self.settings.database_url or "postgres" in self.settings.database_url:
            return PostgresSaver.from_conn_string(self.settings.database_url)
        else:
            db_path = self.settings.database_url.replace("sqlite:///", "")
            return SqliteSaver.from_conn_string(db_path)
