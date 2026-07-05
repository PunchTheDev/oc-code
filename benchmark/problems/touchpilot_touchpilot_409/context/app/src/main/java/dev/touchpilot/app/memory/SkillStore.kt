package dev.touchpilot.app.memory

import android.content.Context
import dev.touchpilot.app.tools.AndroidToolCatalog

class SkillStore(
    context: Context,
    private val knownTools: Set<String> = AndroidToolCatalog.initialTools.map { it.name }.toSet()
) {
    private val assets = context.applicationContext.assets

    /** Valid bundled skills only. Kept for callers that do not need diagnostics. */
    fun loadSkills(): List<Skill> = load().skills

    /** Parses every bundled skill, separating valid skills from invalid files. */
    fun load(): SkillLoad {
        val results = runCatching {
            assets.list(SkillsRoot).orEmpty()
                .sorted()
                .mapNotNull { id -> parseSkill(id) }
        }.getOrDefault(emptyList())

        return SkillLoad(
            skills = results.filterIsInstance<SkillParseResult.Valid>().map { it.skill },
            invalid = results.filterIsInstance<SkillParseResult.Invalid>()
        )
    }

    private fun parseSkill(id: String): SkillParseResult? {
        val markdown = runCatching {
            assets.open("$SkillsRoot/$id/SKILL.md").bufferedReader().use { it.readText() }
        }.getOrNull() ?: return null
        return SkillParser.parse(id, markdown, knownTools)
    }

    private companion object {
        const val SkillsRoot = "skills"
    }
}
