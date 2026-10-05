<template>
  <div class="chat-page">
    <div class="chat-panel">
      <!-- 顶部说明 -->
      <div class="chat-header-hint">
        <el-icon><MagicStick /></el-icon>
        智能客服统一入口：自动识别意图 → 单诉求短路直出 / 多诉求并行汇总 / 需人工自动转接
      </div>

      <!-- 消息区 -->
      <div class="chat-messages" ref="messagesEl">
        <div v-if="messages.length === 0 && !isStreaming" class="empty-hint">
          <p>👋 您好！我是电商智能客服</p>
          <p>可以直接对我说需求，例如：</p>
          <div class="example-queries">
            <el-tag
              v-for="q in exampleQueries"
              :key="q"
              class="example-tag"
              @click="sendExample(q)"
            >{{ q }}</el-tag>
          </div>
        </div>

        <template v-for="(msg, i) in messages" :key="i">
          <!-- 意图识别卡片（统一入口协议：intents/display/provider/mode） -->
          <IntentCard
            v-if="msg.intent"
            :display="msg.intent.display"
            :confidence="msg.intent.confidence"
            :provider="msg.intent.provider"
            :mode="msg.intent.mode"
          />

          <!-- 转人工交接卡片 -->
          <HandoffCard v-if="msg.handoff" :summary="msg.handoff.summary" :reason="msg.handoff.reason" />

          <ChatBubble :role="msg.role" :sources="msg.sources">
            <template v-if="msg.guidance">
              <p style="margin: 0">{{ msg.guidance.message }}</p>
            </template>
            <MarkdownRenderer v-else :content="msg.content" />
          </ChatBubble>
        </template>

        <!-- 流式气泡 -->
        <template v-if="isStreaming">
          <IntentCard
            v-if="streamingIntent"
            :display="streamingIntent.display"
            :confidence="streamingIntent.confidence"
            :provider="streamingIntent.provider"
            :mode="streamingIntent.mode"
          />
          <HandoffCard
            v-if="streamingHandoff"
            :summary="streamingHandoff.summary"
            :reason="streamingHandoff.reason"
          />
          <ChatBubble role="assistant">
            <template v-if="streamingText">
              <MarkdownRenderer :content="streamingText" />
            </template>
            <span v-else-if="progressStage" class="progress-hint">
              <span class="dot" /><span class="dot" /><span class="dot" />
              {{ progressStage }}
            </span>
            <span v-else class="thinking">
              <span class="dot" /><span class="dot" /><span class="dot" />
            </span>
          </ChatBubble>
        </template>
      </div>

      <!-- 输入区 -->
      <div class="chat-input-area">
        <el-input
          ref="inputRef"
          v-model="inputText"
          type="textarea"
          :rows="3"
          placeholder="直接描述您的需求，Enter 发送，Shift+Enter 换行"
          resize="none"
          :disabled="isStreaming"
          @keydown="handleKeydown"
        />
        <div class="input-actions">
          <el-tag v-if="lastRouteProvider === 'cache'" size="small" type="success" effect="plain">
            路由缓存命中
          </el-tag>
          <el-tag v-if="lastAnswerMode" size="small" :type="answerModeTagType">
            {{ answerModeLabel }}
          </el-tag>
          <el-button
            type="primary"
            :loading="isStreaming"
            :disabled="!inputText.trim() || isStreaming"
            @click="sendMessage"
          >
            发送
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import ChatBubble from '@/components/chat/ChatBubble.vue'
import MarkdownRenderer from '@/components/chat/MarkdownRenderer.vue'
import IntentCard from '@/components/chat/IntentCard.vue'
import HandoffCard from '@/components/chat/HandoffCard.vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

interface IntentInfo {
  display: string[]
  confidence: number
  provider: string
  mode: string
}

interface HandoffInfo {
  summary: string
  reason?: string
}

interface GuidanceInfo {
  message: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: string[]
  intent?: IntentInfo
  handoff?: HandoffInfo
  guidance?: GuidanceInfo
}

const messages = ref<Message[]>([])
const inputText = ref('')
const messagesEl = ref<HTMLElement>()
const inputRef = ref()
// 固定 session：同一用户始终复用同一 thread，避免 MemorySaver 无限累积
const sessionId = ref(`unified_${auth.user?.userId ?? 'guest'}`)

const isStreaming = ref(false)
const streamingText = ref('')
const streamingIntent = ref<IntentInfo | null>(null)
const streamingHandoff = ref<HandoffInfo | null>(null)
const progressStage = ref('')
const lastAnswerMode = ref('')
const lastConfidence = ref(0)
const lastSources = ref<string[]>([])
const lastRouteProvider = ref('')

const exampleQueries = [
  '耳机保修多久？',
  '我的订单 A1024 到哪了？',
  '帮我申请退货 A1021',
  '耳机拆封了还能退吗？',
  '转人工',
]

const answerModeTagType = computed(() => {
  if (lastAnswerMode.value === 'rag') return 'success'
  if (lastAnswerMode.value === 'llm_direct') return 'warning'
  return 'info'
})

const answerModeLabel = computed(() => {
  const map: Record<string, string> = {
    rag: `RAG ${lastConfidence.value}%`,
    llm_direct: 'LLM直答（降级兜底）',
    general: '通用回答',
  }
  return map[lastAnswerMode.value] ?? lastAnswerMode.value
})

function sendExample(q: string) {
  inputText.value = q
  sendMessage()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.isComposing) return
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  inputText.value = ''
  messages.value.push({ role: 'user', content: text })
  await scrollToBottom()

  isStreaming.value = true
  streamingText.value = ''
  streamingIntent.value = null
  streamingHandoff.value = null
  progressStage.value = ''
  lastAnswerMode.value = ''
  lastSources.value = []
  lastRouteProvider.value = ''

  let pendingIntent: IntentInfo | null = null
  let pendingHandoff: HandoffInfo | null = null
  let pendingGuidance: GuidanceInfo | null = null

  try {
    const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'
    const resp = await fetch(`${apiBase}/api/v1/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${auth.token}`,
      },
      body: JSON.stringify({
        session_id: sessionId.value,
        message: text,
      }),
    })

    if (resp.status === 401) {
      localStorage.removeItem('edu-agent-token')
      localStorage.removeItem('edu-agent-user')
      router.push('/login')
      return
    }
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() ?? ''

      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (!raw) continue

        try {
          const evt = JSON.parse(raw)

          if (evt.type === 'routing_decision') {
            pendingIntent = {
              display: evt.display ?? [],
              confidence: evt.confidence ?? 0,
              provider: evt.provider ?? '',
              mode: evt.mode ?? '',
            }
            streamingIntent.value = pendingIntent
            await scrollToBottom()

          } else if (evt.type === 'progress') {
            progressStage.value = evt.stage

          } else if (evt.type === 'token') {
            progressStage.value = ''
            streamingText.value += evt.content
            await scrollToBottom()

          } else if (evt.type === 'handoff') {
            pendingHandoff = { summary: evt.summary ?? '', reason: evt.reason }
            streamingHandoff.value = pendingHandoff
            await scrollToBottom()

          } else if (evt.type === 'guidance') {
            pendingGuidance = { message: evt.message }

          } else if (evt.type === 'meta') {
            const modes = (evt.answer_modes ?? {}) as Record<string, string>
            lastAnswerMode.value = modes.product ?? Object.values(modes)[0] ?? ''
            lastConfidence.value = Math.round((evt.confidence ?? 0) * 100)
            lastSources.value = evt.sources ?? []
            lastRouteProvider.value = evt.provider ?? ''

          } else if (evt.type === 'error') {
            throw new Error(evt.message ?? 'SSE error')
          }
        } catch {
          // 忽略非 JSON 行
        }
      }
    }

    // 流结束：将流式内容固化为消息
    if (pendingGuidance) {
      messages.value.push({
        role: 'assistant',
        content: pendingGuidance.message,
        intent: pendingIntent ?? undefined,
        handoff: pendingHandoff ?? undefined,
        guidance: pendingGuidance,
      })
    } else if (streamingText.value || pendingHandoff) {
      messages.value.push({
        role: 'assistant',
        content: streamingText.value,
        sources: lastSources.value,
        intent: pendingIntent ?? undefined,
        handoff: pendingHandoff ?? undefined,
      })
    }
  } catch (err) {
    ElMessage.error('请求失败，请重试')
    console.error('[UnifiedChat SSE]', err)
  } finally {
    isStreaming.value = false
    streamingText.value = ''
    streamingIntent.value = null
    streamingHandoff.value = null
    progressStage.value = ''
    await scrollToBottom()
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-page {
  display: flex;
  height: calc(100vh - 56px - 48px);
}
.chat-panel {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.chat-header-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  font-size: 13px;
  color: #8c8c8c;
  border-bottom: 1px solid #f0f0f0;
  background: #fafafa;
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}
.empty-hint {
  text-align: center;
  color: #8c8c8c;
  margin-top: 60px;
  font-size: 15px;
  line-height: 2;
}
.example-queries {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
}
.example-tag {
  cursor: pointer;
  transition: opacity 0.15s;
}
.example-tag:hover { opacity: 0.75; }
.chat-input-area {
  border-top: 1px solid #f0f0f0;
  padding: 12px 16px;
}
.input-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.thinking, .progress-hint {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 0;
  font-size: 13px;
  color: #8c8c8c;
}
.dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #bfbfbf;
  animation: bounce 1.2s infinite ease-in-out;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.7); opacity: 0.4; }
  40%            { transform: scale(1.1); opacity: 1; }
}
</style>