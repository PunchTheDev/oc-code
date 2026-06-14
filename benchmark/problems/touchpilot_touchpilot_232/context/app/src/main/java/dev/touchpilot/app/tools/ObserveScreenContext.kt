package dev.touchpilot.app.tools

import dev.touchpilot.app.screen.ScreenContext

/**
 * Builds the [ToolResult] and the developer-log message for the
 * `observe_screen_context` tool.
 *
 * Extracted as a pure function so the not-connected failure path can be unit
 * tested without an Android [android.content.Context], and so the exact failure
 * reason is surfaced in logs (issue #216) instead of the misleading
 * `"context nodes=0"`, which reads like a successful but empty observation.
 *
 * When the accessibility service is not connected the tool cannot observe the
 * screen at all; the result and the log entry both carry the precise reason so
 * the Logs detail card and the Tools result panel show why the call failed.
 */
object ObserveScreenContext {
    const val NotConnectedReason: String =
        "TouchPilot Control (accessibility service) is not connected, so the " +
            "screen context could not be observed."

    const val NotConnectedReasonCode: String = "accessibility_not_connected"

    data class Outcome(val result: ToolResult, val logMessage: String)

    fun outcome(connected: Boolean, context: ScreenContext): Outcome {
        if (!connected) {
            return Outcome(
                result = ToolResult(
                    ok = false,
                    message = NotConnectedReason,
                    data = mapOf("reason" to NotConnectedReasonCode)
                ),
                logMessage = NotConnectedReason
            )
        }

        return Outcome(
            result = ToolResult(
                ok = true,
                message = context.toRedactedJson(),
                data = mapOf(
                    "nodes" to context.nodes.size.toString(),
                    "contains_sensitive_content" to context.containsSensitiveContent.toString()
                )
            ),
            logMessage = "context nodes=${context.nodes.size}"
        )
    }
}