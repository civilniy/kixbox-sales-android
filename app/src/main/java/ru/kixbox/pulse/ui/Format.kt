package ru.kixbox.pulse.ui

import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToLong

private val RU = Locale.forLanguageTag("ru-RU")
private const val NBSP = ' '

/** Целое с пробелами-разделителями тысяч: 12 940 682. */
fun groupInt(v: Double): String {
    val n = v.roundToLong()
    val s = abs(n).toString()
    val sb = StringBuilder()
    s.forEachIndexed { i, c ->
        if (i > 0 && (s.length - i) % 3 == 0) sb.append(NBSP)
        sb.append(c)
    }
    return (if (n < 0) "−" else "") + sb
}

private fun dec(v: Double, digits: Int): String =
    String.format(RU, "%.${digits}f", v).replace('-', '−')

/** Деньги компактно: 12,9 млн ₽ · 845 тыс ₽ · 9 990 ₽. */
fun money(v: Double?, currency: Boolean = true, precise: Boolean = false): String {
    if (v == null) return "—"
    val a = abs(v)
    val cur = if (currency) "$NBSP₽" else ""
    return when {
        a >= 1e9 -> dec(v / 1e9, 2) + "${NBSP}млрд$cur"
        a >= 1e6 -> dec(v / 1e6, if (a >= 1e8) 0 else if (precise || a < 1e7) 2 else 1) + "${NBSP}млн$cur"
        a >= 1e4 -> groupInt(v / 1e3) + "${NBSP}тыс$cur"
        else -> groupInt(v) + cur
    }
}

fun moneyFull(v: Double?): String = if (v == null) "—" else groupInt(v) + "$NBSP₽"

fun pct(v: Double?, signed: Boolean = false): String {
    if (v == null) return "—"
    val x = v * 100
    val d = if (abs(x) < 1 && x != 0.0) 2 else 1
    val s = dec(x, d)
    return (if (signed && x > 0) "+" else "") + s + "%"
}

fun formatValue(v: Double?, format: String, compact: Boolean = true): String {
    if (v == null) return "—"
    return when (format) {
        "money" -> if (compact) money(v) else moneyFull(v)
        "int" -> if (compact && abs(v) >= 1e6) dec(v / 1e6, 2) + "${NBSP}млн" else groupInt(v)
        "pct" -> pct(v)
        "dec1" -> dec(v, 1)
        "dec2" -> dec(v, 2)
        "days" -> dec(v, 1) + "${NBSP}дн"
        "sec" -> {
            val s = v.roundToLong()
            "${s / 60}:${(s % 60).toString().padStart(2, '0')}"
        }
        else -> dec(v, 0)
    }
}

/** Для осей и подписей графика. */
fun axisValue(v: Double, format: String): String = when (format) {
    "money" -> money(v, currency = false)
    "pct" -> pct(v)
    "int" -> if (abs(v) >= 1e6) dec(v / 1e6, 1) + "м" else if (abs(v) >= 1e4) groupInt(v / 1e3) + "к" else groupInt(v)
    else -> formatValue(v, format)
}

fun deltaText(d: Double?, kind: String): String {
    if (d == null) return ""
    return if (kind == "pp") {
        val x = d * 100
        (if (x > 0) "+" else "") + dec(x, 1) + "${NBSP}п.п."
    } else {
        val x = d * 100
        when {
            abs(x) >= 1000 -> (if (x > 0) "×" else "") + dec(1 + d, 0)
            else -> (if (x > 0) "+" else "") + dec(x, if (abs(x) < 10) 1 else 0) + "%"
        }
    }
}

fun shortDate(iso: String?): String {
    if (iso.isNullOrBlank()) return "—"
    return runCatching {
        LocalDate.parse(iso.take(10)).format(DateTimeFormatter.ofPattern("dd.MM", RU))
    }.getOrDefault(iso)
}

fun timeStamp(iso: String?): String {
    if (iso.isNullOrBlank()) return "—"
    return runCatching {
        OffsetDateTime.parse(iso).format(DateTimeFormatter.ofPattern("dd.MM HH:mm", RU))
    }.getOrDefault(iso)
}
