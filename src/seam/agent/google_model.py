"""Keep native Gemini requests inside the controller's per-call accounting."""

from google.genai.types import ContentUnionDict, GenerateContentConfigDict
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings


class BoundedGoogleModel(GoogleModel):
    """Disable SDK follow-up requests which would bypass the usage ledger."""

    async def _build_content_and_config(
        self,
        messages: list[ModelMessage],
        model_settings: GoogleModelSettings,
        model_request_parameters: ModelRequestParameters,
    ) -> tuple[list[ContentUnionDict], GenerateContentConfigDict]:
        # shortcut: upstream lacks these public settings; remove when it exposes them.
        contents, config = await super()._build_content_and_config(
            messages, model_settings, model_request_parameters
        )
        config["automatic_continuation"] = False
        config["automatic_function_calling"] = {"disable": True}
        return contents, config
