<template>
  <div class="pool-page">
    <div class="page-head">
      <h3>未解决问题池 · 转人工记录</h3>
      <el-button size="small" :loading="loading" @click="load">刷新</el-button>
    </div>
    <p class="hint">用户要求转人工 / 低置信兜底 / 投诉升级时，系统会自动生成交接摘要并入池。</p>

    <el-table :data="items" v-loading="loading" stripe empty-text="暂无待处理记录">
      <el-table-column prop="id" label="#" width="70" />
      <el-table-column prop="question" label="用户问题" min-width="200" show-overflow-tooltip />
      <el-table-column label="交接摘要" min-width="360">
        <template #default="{ row }"><div class="summary">{{ row.summary }}</div></template>
      </el-table-column>
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'resolved' ? 'success' : 'warning'">
            {{ row.status === 'resolved' ? '已解决' : '待处理' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="时间" width="180" />
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status !== 'resolved'"
            size="small"
            type="primary"
            link
            @click="resolve(row)"
          >标记已解决</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listUnresolved, resolveUnresolved, type UnresolvedItem } from '@/api/console'

const loading = ref(false)
const items = ref<UnresolvedItem[]>([])

async function load() {
  loading.value = true
  try {
    const res = await listUnresolved()
    items.value = res.items ?? []
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function resolve(row: UnresolvedItem) {
  try {
    await resolveUnresolved(row.id)
    ElMessage.success(`#${row.id} 已标记为解决`)
    await load()
  } catch {
    // 拦截器已提示
  }
}

onMounted(load)
</script>

<style scoped>
.pool-page { max-width: 1200px; }
.page-head { display: flex; align-items: center; justify-content: space-between; }
.page-head h3 { margin: 0 0 4px; }
.hint { color: #8c8c8c; font-size: 13px; margin: 4px 0 14px; }
.summary {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12.5px;
  color: #595959;
  max-height: 120px;
  overflow: auto;
}
</style>