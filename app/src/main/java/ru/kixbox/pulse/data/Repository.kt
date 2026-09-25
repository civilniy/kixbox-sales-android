package ru.kixbox.pulse.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class ApiException(message: String, val code: Int = 0) : Exception(message)

/** Адрес сервера, токен и кэш последних ответов живут только в настройках телефона. */
class Repository(context: Context) {
    private val prefs = context.getSharedPreferences("pulse", Context.MODE_PRIVATE)

    var endpoint: String
        get() = prefs.getString("endpoint", "") ?: ""
        private set(v) = prefs.edit().putString("endpoint", v).apply()

    var token: String
        get() = prefs.getString("token", "") ?: ""
        private set(v) = prefs.edit().putString("token", v).apply()

    var lastPeriod: String
        get() = prefs.getString("period", "mtd") ?: "mtd"
        set(v) = prefs.edit().putString("period", v).apply()

    var lastSection: Int
        get() = prefs.getInt("section", 0)
        set(v) = prefs.edit().putInt("section", v).apply()

    val configured: Boolean get() = endpoint.isNotBlank() && token.isNotBlank()

    fun saveConnection(url: String, tok: String) {
        endpoint = url.trim().trimEnd('/')
        token = tok.trim()
    }

    fun cachedMeta(): Meta? = prefs.getString("meta", null)?.let { runCatching { parseMeta(it) }.getOrNull() }

    fun cachedSection(id: String, period: String): SectionPayload? =
        prefs.getString("s:$id:$period", null)?.let { runCatching { parseSection(it) }.getOrNull() }

    suspend fun meta(refresh: Boolean = false): Meta {
        val raw = get("/api/v1/meta" + if (refresh) "?refresh=true" else "")
        val meta = parseMeta(raw)
        prefs.edit().putString("meta", raw).apply()
        return meta
    }

    suspend fun section(id: String, period: String, refresh: Boolean = false): SectionPayload {
        val q = "period=" + URLEncoder.encode(period, "UTF-8") + if (refresh) "&refresh=true" else ""
        val raw = get("/api/v1/section/$id?$q")
        val payload = parseSection(raw)
        if (payload.error == null) prefs.edit().putString("s:$id:$period", raw).apply()
        return payload
    }

    suspend fun ping(url: String, tok: String): String = withContext(Dispatchers.IO) {
        val base = url.trim().trimEnd('/')
        val health = request("$base/api/v1/health", null)
        if (!health.contains("\"ok\"")) throw ApiException("Сервер ответил, но это не KIXBOX Pulse API")
        request("$base/api/v1/meta", tok.trim())
        "Соединение установлено"
    }

    private suspend fun get(path: String): String = withContext(Dispatchers.IO) {
        if (!configured) throw ApiException("Сервер не настроен")
        request(endpoint + path, token)
    }

    private fun request(url: String, tok: String?): String {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 15_000
        c.readTimeout = 120_000
        c.setRequestProperty("Accept", "application/json")
        if (!tok.isNullOrBlank()) c.setRequestProperty("Authorization", "Bearer $tok")
        try {
            val code = c.responseCode
            if (code !in 200..299) {
                val msg = when (code) {
                    401 -> "Неверный токен доступа"
                    404 -> "Адрес не найден — проверьте ссылку на сервер"
                    502, 503, 504 -> "Сервер недоступен (HTTP $code)"
                    else -> "Сервер вернул HTTP $code"
                }
                throw ApiException(msg, code)
            }
            return c.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } catch (e: ApiException) {
            throw e
        } catch (e: java.net.UnknownHostException) {
            throw ApiException("Нет связи с сервером: адрес не найден")
        } catch (e: java.net.SocketTimeoutException) {
            throw ApiException("Сервер не ответил вовремя")
        } catch (e: java.io.IOException) {
            throw ApiException("Нет связи с сервером: ${e.message ?: "ошибка сети"}")
        } finally {
            c.disconnect()
        }
    }
}
