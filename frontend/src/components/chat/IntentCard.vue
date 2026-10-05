<template>
  <div class="intent-card">
    <span class="label">意图识别</span>
    <el-tag v-for="d in display" :key="d" size="small" effect="plain" type="primary">{{ d }}</el-tag>
    <el-tag v-if="modeLabel" size="small" :type="modeType" effect="light">{{ modeLabel }}</el-tag>
    <el-tag v-if="provider === 'cache'" size="small" type="success" effect="plain">路由缓存命中</el-tag>
    <span class="conf">置信度 {{ Math.round((confidence || 0) * 100) }}%</span>
    <span v-if="provider && provider !== 'cache'" class="provider">via {{ provider }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  display: string[]
  confidence: number
  provider?: string
  mode?: string
}>()

const modeLabel = computed(() => {
  const map: Record<string, string> = {
    short_circuit: '短路直出',
    single: '单意图处理',
    parallel: '多意图并行',
    human: '转人工',
  }
  return map[props.mode ?? ''] ?? (props.mode || '')
})

const modeType = computed(() => {
  if (props.mode === 'parallel') return 'warning'
  if (props.mode === 'human') return 'danger'
  return 'success'
})
</script>

<style scoped>
.intent-card {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  padding: 6px 2px;
  margin-bottom: 4px;
  font-size: 12px;
  color: #8c8c8c;
}
.intent-card .label { color: #595959; font-weight: 600; }
.intent-card .conf { margin-left: 2px; }
.intent-card .provider { color: #bfbfbf; }
</style>