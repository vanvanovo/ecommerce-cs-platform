<template>
  <div class="dashboard">
    <div class="welcome">
      <h2>欢迎回来，{{ auth.user?.username ?? auth.user?.userId }}</h2>
      <p>电商多 Agent 智能客服平台 · 统一入口 + 主管审批 + 未解决问题池</p>
    </div>

    <!-- 智能客服入口（突出展示） -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="24">
        <el-card
          class="ai-assistant-card"
          shadow="hover"
          @click="router.push('/chat')"
        >
          <div class="ai-card-content">
            <div class="ai-card-left">
              <span class="ai-icon">🛒</span>
              <div>
                <div class="ai-title">智能客服</div>
                <div class="ai-desc">
                  商品咨询 / 订单物流 / 售后办理 / 投诉安抚 — 自动识别意图，多诉求并行处理，需要时自动转人工
                </div>
              </div>
            </div>
            <el-button type="primary" size="default">立即体验 →</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 运营数据（来自 /api/v1/console/overview） -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6" v-for="s in stats" :key="s.label">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ s.value }}</div>
          <div class="stat-label">{{ s.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 功能 / 引导卡片 -->
    <el-row :gutter="16" class="feature-cards">
      <el-col :span="6" v-for="card in featureCards" :key="card.title">
        <el-card
          class="feature-card"
          shadow="hover"
          @click="router.push(card.route)"
        >
          <div class="card-icon">{{ card.icon }}</div>
          <div class="card-title">{{ card.title }}</div>
          <div class="card-desc">{{ card.desc }}</div>
          <el-button type="primary" plain size="small" style="margin-top: 12px">
            {{ card.action }}
          </el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getOverview, type OverviewData } from '@/api/console'

const router = useRouter()
const auth = useAuthStore()
const overview = ref<OverviewData | null>(null)

onMounted(async () => {
  try {
    overview.value = await getOverview()
  } catch {
    // 接口异常时静态展示，不打扰用户
  }
})

const stats = computed(() => {
  const o = overview.value
  const m = o?.metrics ?? {}
  const cacheHits =
    (m.route_cache_hit ?? 0) + (m.rag_cache_hit ?? 0) + (m.logistics_cache_hit ?? 0)
  return [
    { label: '待审批单（HitL）', value: o ? o.pending_reviews : '-' },
    { label: '未解决问题', value: o ? o.unresolved_questions : '-' },
    { label: '售后工单', value: o ? o.tickets_total : '-' },
    { label: '缓存命中次数', value: o ? cacheHits : '-' },
  ]
})

const featureCards = computed(() => {
  const cards = [
    { icon: '💬', title: '智能客服', desc: '试试：耳机保修多久？', action: '去对话', route: '/chat' },
    { icon: '📦', title: '订单物流', desc: '试试：我的订单 A1024 到哪了？', action: '去对话', route: '/chat' },
    { icon: '🧾', title: '售后办理', desc: '试试：帮我申请退货 A1021（≥500 转主管审批）', action: '去对话', route: '/chat' },
  ]
  if (auth.isTeacher) {
    cards.push({ icon: '✅', title: '主管审批', desc: 'HitL 暂停的售后申请等待审批后恢复执行', action: '去审批', route: '/reviews' })
    cards.push({ icon: '📮', title: '未解决问题池', desc: '转人工记录与交接摘要，可标记已解决', action: '查看', route: '/unresolved' })
  }
  return cards
})
</script>

<style scoped>
.dashboard {
  max-width: 1100px;
}
.welcome {
  margin-bottom: 24px;
}
.welcome h2 {
  margin: 0 0 4px;
  font-size: 22px;
}
.welcome p {
  margin: 0;
  color: #8c8c8c;
}
.ai-assistant-card {
  cursor: pointer;
  background: linear-gradient(135deg, #f0f7ff 0%, #e6f4ff 100%);
  border: 1px solid #bae0ff;
  transition: transform 0.2s;
}
.ai-assistant-card:hover { transform: translateY(-2px); }
.ai-card-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
}
.ai-card-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.ai-icon { font-size: 36px; }
.ai-title {
  font-size: 17px;
  font-weight: 600;
  color: #1677ff;
  margin-bottom: 4px;
}
.ai-desc {
  font-size: 13px;
  color: #595959;
}
.stat-row { margin-bottom: 16px; }
.stat-card {
  text-align: center;
  background: #fafcff;
}
.stat-value {
  font-size: 26px;
  font-weight: 700;
  color: #1677ff;
  line-height: 1.4;
}
.stat-label {
  font-size: 12.5px;
  color: #8c8c8c;
}
.feature-card {
  cursor: pointer;
  text-align: center;
  padding: 8px 0;
  transition: transform 0.2s;
  margin-bottom: 16px;
}
.feature-card:hover {
  transform: translateY(-2px);
}
.card-icon {
  font-size: 40px;
  margin-bottom: 12px;
}
.card-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}
.card-desc {
  font-size: 13px;
  color: #8c8c8c;
  line-height: 1.5;
  min-height: 48px;
}
</style>