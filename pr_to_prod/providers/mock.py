"""Mock LLM provider for testing and offline mode."""

import hashlib
import logging
from typing import Any

from pr_to_prod.providers.base import BaseLLMProvider, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class MockProvider(BaseLLMProvider):
    """Mock LLM provider that generates deterministic responses."""

    def __init__(self, deterministic: bool = True):
        self.deterministic = deterministic
        self.call_count = 0

    async def generate(
        self,
        messages: list[LLMMessage],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a mock response based on the input."""
        self.call_count += 1

        last_message = messages[-1].content if messages else ""
        
        if "plan" in last_message.lower():
            content = self._generate_plan_response()
        elif "code" in last_message.lower() or "implement" in last_message.lower():
            content = self._generate_code_response()
        elif "review" in last_message.lower():
            content = self._generate_review_response()
        elif "test" in last_message.lower():
            content = self._generate_test_response()
        elif "deploy" in last_message.lower():
            content = self._generate_deploy_response()
        elif "report" in last_message.lower():
            content = self._generate_report_response()
        else:
            content = self._generate_generic_response(last_message)

        prompt_tokens = sum(len(m.content.split()) * 2 for m in messages)
        completion_tokens = len(content.split()) * 2

        return LLMResponse(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model=f"mock-{model}",
            finish_reason="stop",
        )

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """Mock provider has zero cost."""
        return 0.0

    def _generate_plan_response(self) -> str:
        """Generate a mock planning response."""
        return """
## Plan Summary
I will implement the requested feature by modifying the main application files and adding necessary tests.

## Files to Change
- app/main.py
- app/models.py
- tests/test_main.py

## Acceptance Criteria
1. Feature is implemented according to the issue description
2. All existing tests pass
3. New tests cover the new functionality
4. Code follows project style guidelines

## Tests Needed
- Unit tests for new functionality
- Integration tests for API endpoints
- Edge case validation

## Estimated Complexity
Medium - straightforward implementation with standard patterns

## Risks
- Potential breaking changes to existing API
- Database migration may be needed
"""

    def _generate_code_response(self) -> str:
        """Generate a mock coding response."""
        return """
## Implementation Complete

I have successfully implemented the requested changes:

### Changes Made:
1. **app/main.py**: Added new endpoint `/api/feature`
2. **app/models.py**: Created `Feature` model with required fields
3. **tests/test_main.py**: Added comprehensive test coverage

### Branch Information:
- Branch: agent/issue-123-add-feature
- Commits: 1 commit with all changes
- Status: Ready for review

All linting and unit tests pass locally.
"""

    def _generate_review_response(self) -> str:
        """Generate a mock review response."""
        return """
## Code Review

I have reviewed the changes and they look good overall.

### Positive Aspects:
- Clean code structure
- Good test coverage
- Follows project conventions

### Minor Suggestions:
- Consider adding error handling for edge cases
- Documentation could be more detailed

### Decision: **APPROVED**

The code meets our quality standards and is ready to proceed.
"""

    def _generate_test_response(self) -> str:
        """Generate a mock test response."""
        return """
## Test Results

All tests have been added and are passing successfully.

### Tests Added:
- test_feature_creation
- test_feature_validation
- test_feature_api_endpoints

### Test Summary:
- Tests Passed: 15
- Tests Failed: 0
- Coverage: 95%

CI pipeline completed successfully.
"""

    def _generate_deploy_response(self) -> str:
        """Generate a mock deployment response."""
        return """
## Deployment Complete

Successfully deployed to staging environment.

### Deployment Details:
- Environment: staging
- Deployment Time: 2 minutes
- Health Check: PASSED
- Error Rate: 0.1% (within threshold)

The application is healthy and ready for production promotion.
"""

    def _generate_report_response(self) -> str:
        """Generate a mock report response."""
        return """
## Summary Report

Successfully completed the PR-to-production workflow.

### Workflow Summary:
- **Issue**: #123 - Add new feature
- **PR**: #456 - Merged successfully
- **Deployment**: Staging deployment successful
- **Status**: ✅ COMPLETED

### Metrics:
- Total Time: 15 minutes
- Token Usage: 25,000 tokens
- Estimated Cost: $0.15
- Retries: 0

The feature has been successfully deployed and is now available in staging.
"""

    def _generate_generic_response(self, input_text: str) -> str:
        """Generate a generic mock response."""
        if self.deterministic:
            hash_val = hashlib.md5(input_text.encode()).hexdigest()[:8]
            return f"Mock response generated for input hash: {hash_val}\n\nProcessing complete."
        return f"Mock response to: {input_text[:100]}...\n\nTask completed successfully."
