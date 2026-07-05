package dev.touchpilot.app.mcp

data class McpTool(
    val name: String,
    val description: String
)

data class McpToolCallResult(
    val ok: Boolean,
    val message: String
)
