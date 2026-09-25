package ru.kixbox.pulse

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import ru.kixbox.pulse.data.Meta
import ru.kixbox.pulse.data.PeriodInfo
import ru.kixbox.pulse.data.Repository
import ru.kixbox.pulse.data.SectionInfo
import ru.kixbox.pulse.data.SectionPayload

data class PageState(
    val payload: SectionPayload? = null,
    val loading: Boolean = false,
    val error: String? = null,
    val fromCache: Boolean = false,
    val loadedAt: Long = 0L
)

val DEFAULT_SECTIONS = listOf(
    SectionInfo("overview", "Сводка", "dashboard"),
    SectionInfo("sales", "Продажи ИМ", "cart"),
    SectionInfo("products", "Товары", "tag"),
    SectionInfo("stores", "Магазины", "store"),
    SectionInfo("customers", "Клиенты", "people"),
    SectionInfo("traffic", "Трафик", "traffic"),
    SectionInfo("ads", "Реклама", "ads"),
    SectionInfo("crm", "Рассылки", "mail"),
    SectionInfo("logistics", "Доставка", "truck"),
    SectionInfo("stock", "Склад", "box"),
    SectionInfo("competitors", "Конкуренты", "radar"),
)

val DEFAULT_PERIODS = listOf(
    PeriodInfo("yesterday", "День"), PeriodInfo("7d", "7 дней"), PeriodInfo("30d", "30 дней"),
    PeriodInfo("mtd", "Месяц"), PeriodInfo("last_month", "Прошлый месяц"), PeriodInfo("qtd", "Квартал"),
    PeriodInfo("90d", "90 дней"), PeriodInfo("ytd", "Год"),
)

class PulseViewModel(app: Application) : AndroidViewModel(app) {
    val repo = Repository(app)

    var configured by mutableStateOf(repo.configured)
        private set
    var meta by mutableStateOf<Meta?>(repo.cachedMeta())
        private set
    var metaError by mutableStateOf<String?>(null)
        private set
    var period by mutableStateOf(repo.lastPeriod)
        private set

    val pages = mutableStateMapOf<String, PageState>()
    private val jobs = mutableMapOf<String, Job>()

    val sections: List<SectionInfo> get() = meta?.sections?.takeIf { it.isNotEmpty() } ?: DEFAULT_SECTIONS
    val periods: List<PeriodInfo> get() = meta?.periods?.takeIf { it.isNotEmpty() } ?: DEFAULT_PERIODS

    init {
        if (configured) loadMeta()
    }

    private fun key(section: String, p: String = period) = "$section:$p"

    fun page(section: String): PageState = pages[key(section)] ?: PageState()

    fun loadMeta(refresh: Boolean = false) {
        viewModelScope.launch {
            try {
                meta = repo.meta(refresh)
                metaError = null
            } catch (e: Exception) {
                metaError = e.message
            }
        }
    }

    /** Открыть раздел: показать кэш сразу и обновить, если данные старше 10 минут. */
    fun ensure(section: String) {
        val k = key(section)
        val st = pages[k]
        if (st != null && (st.loading || System.currentTimeMillis() - st.loadedAt < 10 * 60_000)) return
        load(section, refresh = false)
    }

    fun load(section: String, refresh: Boolean) {
        if (!configured) return
        val p = period
        val k = key(section, p)
        val current = pages[k] ?: repo.cachedSection(section, p)?.let { PageState(payload = it, fromCache = true) }
            ?: PageState()
        pages[k] = current.copy(loading = true, error = null)
        jobs[k]?.cancel()
        jobs[k] = viewModelScope.launch {
            pages[k] = try {
                val payload = repo.section(section, p, refresh)
                PageState(payload = payload, loading = false, error = payload.error?.let { "Сервер не смог собрать раздел" },
                    fromCache = false, loadedAt = System.currentTimeMillis())
            } catch (e: Exception) {
                (pages[k] ?: PageState()).copy(loading = false, error = e.message ?: "Ошибка сети")
            }
        }
    }

    fun refreshAll(currentSection: String) {
        loadMeta(refresh = true)
        pages.keys.filter { !it.startsWith("$currentSection:") }.forEach { pages.remove(it) }
        load(currentSection, refresh = true)
    }

    fun selectPeriod(p: String) {
        period = p
        repo.lastPeriod = p
    }

    fun saveConnection(url: String, token: String) {
        repo.saveConnection(url, token)
        configured = repo.configured
        pages.clear()
        if (configured) loadMeta(refresh = true)
    }

    suspend fun ping(url: String, token: String): Result<String> =
        runCatching { repo.ping(url, token) }
}
