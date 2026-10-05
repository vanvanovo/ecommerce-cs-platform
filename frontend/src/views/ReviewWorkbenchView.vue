<template>
  <div class="review-page">
    <div class="page-head">
      <h3>主管审批 · 售后工单</h3>
      <el-button size="small" :loading="loading" @click="load">刷新</el-button>
    </div>
    <p class="hint">金额 ≥ 500 或已拆封的退换货申请会暂停在图里（HitL），等待主管审批后继续执行。</p>

    <el-table :data="items" v-loading="loading" stripe empty-text="暂无待审批单">
      <el-table-column prop="review_id" label="审批单" width="170" />
      <el-table-column prop="order_id" label="订单号" width="100" />
      <el-table-column prop="ticket_type" label="类型" width="100" />
      <el-table-column label="金额" width="110">
        <template #default="{ row }">{{ row.amount != null ? `¥${row.amount}` : '-' }}</template>
      </el-table-column>
      <el-table-column label="触发原因" min-width="260">
        <template #default="{ row }">
          <el-tag
            v-for="(r, i) in row.reasons"
            :key="i"
            size="small"
            type="warning"
            effect="plain"
            style="margin: 2px 6px 2px 0"
          >{{ r }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="210" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="openDetail(row)">详情</el-button>
          <el-button size="small" type="success" link @click="decide(row, 'approve')">通过</el-button>
          <el-button size="small" type="danger" link @click="decide(row, 'reject')">驳回</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="detailVisible" title="审批详情" width="640px">
      <el-descriptions v-if="detail" :column="1" border size="small">
        <el-descriptions-item label="审批单">{{ detail.review_id }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ detail.status }}</el-descriptions-item>
        <el-descriptions-item label="订单号">{{ detail.payload?.order_id }}</el-descriptions-item>
        <el-descriptions-item label="建议动作">{{ detail.payload?.suggested_action }}</el-descriptions-item>
        <el-descriptions-item label="规则审核结果">
          <pre class="json">{{ JSON.stringify(detail.payload?.check_result ?? detail.payload, null, 2) }}</pre>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="danger" @click="decide(current, 'reject', true)">驳回</el-button>
        <el-button type="primary" @click="decide(current, 'approve', true)">通过</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { confirmReview, getReviewDetail, listPendingReviews, type ReviewItem } from '@/api/console'

const loading = ref(false)
const items = ref<ReviewItem[]>([])
const detailVisible = ref(false)
const detail = ref<any>(null)
const current = ref<ReviewItem | null>(null)

async function load() {
  loading.value = true
  try {
    const res = await listPendingReviews()
    items.value = res.items ?? []
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function openDetail(row: ReviewItem) {
  current.value = row
  detail.value = null
  detailVisible.value = true
  try {
    detail.value = await getReviewDetail(row.review_id)
  } catch {
    // 拦截器已提示
  }
}

async function decide(row: ReviewItem | null, action: 'approve' | 'reject', closeDialog = false) {
  if (!row) return
  let comment = ''
  try {
    const { value } = await ElMessageBox.prompt('请输入审批意见（可留空）', action === 'approve' ? '通过审批' : '驳回审批', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPlaceholder: '审批意见',
    })
    comment = value ?? ''
  } catch {
    return // 用户取消
  }

  try {
    const res = await confirmReview(row.review_id, action, comment)
    ElMessage.success(
      `${action === 'approve' ? '已通过' : '已驳回'}：工单 ${res.ticket_id ?? '-'} → ${res.ticket_status ?? '-'}`,
    )
    if (closeDialog) detailVisible.value = false
    await load()
  } catch {
    // 拦截器已提示
  }
}

onMounted(load)
</script>

<style scoped>
.review-page { max-width: 1200px; }
.page-head { display: flex; align-items: center; justify-content: space-between; }
.page-head h3 { margin: 0 0 4px; }
.hint { color: #8c8c8c; font-size: 13px; margin: 4px 0 14px; }
.json {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  max-height: 300px;
  overflow: auto;
}
</style>