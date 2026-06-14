package dev.touchpilot.app.memory

data class Skill(
    val id: String,
    val title: String,
    val markdown: String,
    val allowedTools: Set<String>
)
