package ru.kixbox.pulse.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

@Immutable
data class Palette(
    val bg: Color,
    val card: Color,
    val cardAlt: Color,
    val ink: Color,
    val muted: Color,
    val faint: Color,
    val line: Color,
    val accent: Color,
    val accentSoft: Color,
    val good: Color,
    val bad: Color,
    val warn: Color,
    val hero: Color,
    val heroInk: Color,
    val series: List<Color>,
    val dark: Boolean
)

val LightPalette = Palette(
    bg = Color(0xFFF3F5F8),
    card = Color.White,
    cardAlt = Color(0xFFF3F5F8),
    ink = Color(0xFF111827),
    muted = Color(0xFF6B7280),
    faint = Color(0xFF9CA3AF),
    line = Color(0xFFE5E7EB),
    accent = Color(0xFF2563EB),
    accentSoft = Color(0xFFDBEAFE),
    good = Color(0xFF15803D),
    bad = Color(0xFFDC2626),
    warn = Color(0xFFB45309),
    hero = Color(0xFF111827),
    heroInk = Color.White,
    series = listOf(
        Color(0xFF2563EB), Color(0xFF93C5FD), Color(0xFFF59E0B), Color(0xFF111827),
        Color(0xFFEF4444), Color(0xFF10B981), Color(0xFF9CA3AF), Color(0xFF8B5CF6)
    ),
    dark = false
)

val DarkPalette = Palette(
    bg = Color(0xFF0B0F17),
    card = Color(0xFF151B26),
    cardAlt = Color(0xFF1D2431),
    ink = Color(0xFFF3F4F6),
    muted = Color(0xFF9CA3AF),
    faint = Color(0xFF6B7280),
    line = Color(0xFF263041),
    accent = Color(0xFF3B82F6),
    accentSoft = Color(0xFF1E3A8A),
    good = Color(0xFF34D399),
    bad = Color(0xFFF87171),
    warn = Color(0xFFFBBF24),
    hero = Color(0xFF1B2433),
    heroInk = Color.White,
    series = listOf(
        Color(0xFF3B82F6), Color(0xFF7DD3FC), Color(0xFFFBBF24), Color(0xFFE5E7EB),
        Color(0xFFF87171), Color(0xFF34D399), Color(0xFF6B7280), Color(0xFFA78BFA)
    ),
    dark = true
)

val LocalPalette = staticCompositionLocalOf { LightPalette }

val P: Palette
    @Composable get() = LocalPalette.current

@Composable
fun PulseTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val p = if (dark) DarkPalette else LightPalette
    val scheme = if (dark) darkColorScheme(
        primary = p.accent, background = p.bg, surface = p.card, onSurface = p.ink, onBackground = p.ink,
        surfaceVariant = p.cardAlt, onSurfaceVariant = p.muted, outline = p.line
    ) else lightColorScheme(
        primary = p.accent, background = p.bg, surface = p.card, onSurface = p.ink, onBackground = p.ink,
        surfaceVariant = p.cardAlt, onSurfaceVariant = p.muted, outline = p.line
    )
    CompositionLocalProvider(LocalPalette provides p) {
        MaterialTheme(colorScheme = scheme, content = content)
    }
}

fun Palette.seriesColor(i: Int?): Color = series[((i ?: 0) % series.size + series.size) % series.size]

fun Palette.tone(t: String): Color = when (t) {
    "good" -> good
    "bad" -> bad
    "warn" -> warn
    else -> accent
}
