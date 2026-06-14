package dev.touchpilot.app.ui.chat

import dev.touchpilot.app.security.PolicyDecision
import dev.touchpilot.app.security.ToolApprovalRequest
import dev.touchpilot.app.tools.ToolRisk
import dev.touchpilot.app.tools.ToolSpec
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ChatToolTextFormatterTest {
    private fun request(skillContext: String) = ToolApprovalRequest(
        tool = ToolSpec(
            name = "tap",
            description = "Tap a target",
            risk = ToolRisk.MEDIUM,
            arguments = mapOf("text" to "Target text")
        ),
        args = mapOf("text" to "Send"),
        policy = PolicyDecision.RequireApproval(
            reason = "medium risk Android action",
            userMessage = "Approval required for tap.",
            dataAffected = "The current app or screen may be changed.",
            ifApproved = "TouchPilot will run tap.",
            skillContext = skillContext
        )
    )

    @Test
    fun rendersSkillContextLineWhenPresent() {
        val note = "This action is requested under the high-risk skill \"Messages\"."
        val text = ChatToolTextFormatter.approvalMessage(request(note))

        assertTrue(text.contains("Skill context: $note"), text)
    }

    @Test
    fun omitsSkillContextLineWhenBlank() {
        val text = ChatToolTextFormatter.approvalMessage(request(""))

        assertFalse(text.contains("Skill context:"), text)
        assertTrue(text.contains("Why approval is needed:"), text)
    }
}