package dev.touchpilot.app.memory

import android.content.Context

class SkillStore(context: Context) {
    private val assets = context.applicationContext.assets

    fun loadSkills(): List<Skill> {
        return runCatching {
            assets.list(SkillsRoot).orEmpty()
                .sorted()
                .mapNotNull { id -> loadSkill(id) }
        }.getOrDefault(emptyList())
    }

    private fun loadSkill(id: String): Skill? {
        val path = "$SkillsRoot/$id/SKILL.md"
        val markdown = runCatching {
            assets.open(path).bufferedReader().use { it.readText() }
        }.getOrNull() ?: return null

        return Skill(
            id = id,
            title = parseTitle(markdown).ifBlank { id },
            markdown = markdown.trim(),
            allowedTools = parseAllowedTools(markdown)
        )
    }

    private fun parseTitle(markdown: String): String {
        return markdown
            .lineSequence()
            .firstOrNull { it.startsWith("# ") }
            ?.removePrefix("# ")
            ?.trim()
            .orEmpty()
    }

    private fun parseAllowedTools(markdown: String): Set<String> {
        val tools = mutableSetOf<String>()
        var inAllowedTools = false

        markdown.lineSequence().forEach { line ->
            val trimmed = line.trim()
            if (trimmed.equals("Allowed initial tools:", ignoreCase = true)) {
                inAllowedTools = true
                return@forEach
            }

            if (inAllowedTools && trimmed.startsWith("#")) {
                inAllowedTools = false
            }

            if (inAllowedTools && trimmed.startsWith("-")) {
                Regex("`([^`]+)`").find(trimmed)?.groupValues?.getOrNull(1)?.let { tool ->
                    tools.add(tool)
                }
            }
        }

        return tools
    }

    private companion object {
        const val SkillsRoot = "skills"
    }
}
