<template>
  <div class="handoff-card">
    <div class="handoff-head">
      <el-icon><Service /></el-icon>
      <span>已转人工客服</span>
      <span v-if="reason" class="reason">（{{ reason }}）</span>
    </div>
    <div class="handoff-body">
      <div class="sub">交接摘要（人工客服可见，用户无需重复描述）</div>
      <pre>{{ summary }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Service } from '@element-plus/icons-vue'

defineProps<{ summary: string; reason?: string }>()
</script>

<style scoped>
.handoff-card {
  border: 1px solid #ffd591;
  background: #fff7e6;
  border-radius: 8px;
  padding: 10px 14px;
  margin: 6px 0;
  font-size: 13px;
}
.handoff-head {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #d46b08;
  font-weight: 600;
  margin-bottom: 6px;
}
.handoff-head .reason { color: #ad6800; font-weight: 400; font-size: 12px; }
.handoff-body .sub { color: #8c8c8c; font-size: 12px; margin-bottom: 4px; }
.handoff-body pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: #614700;
  font-family: inherit;
  font-size: 12.5px;
  line-height: 1.6;
}
</style>