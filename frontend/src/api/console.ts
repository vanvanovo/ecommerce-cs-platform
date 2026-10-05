// frontend/src/api/console.ts
// 运营台接口（P6）：主管审批 / 未解决问题池 / 总览统计

import client from './client'

export interface ReviewItem {
  review_id: string
  order_id?: string
  ticket_type?: string
  amount?: number
  suggested_action?: string
  reasons: string[]
  created_at?: number
}

export interface UnresolvedItem {
  id: number
  session_id: string
  question: string
  summary: string
  status: string
  created_at: string
}

export interface OverviewData {
  pending_reviews: number
  unresolved_questions: number
  tickets_total: number
  tickets_by_status: Record<string, number>
  metrics: Record<string, number>
}

export async function listPendingReviews(): Promise<{ count: number; items: ReviewItem[] }> {
  return (await client.get('/aftersale/reviews')).data
}

export async function getReviewDetail(reviewId: string) {
  return (await client.get(`/aftersale/review/${reviewId}`)).data
}

export async function confirmReview(reviewId: string, action: string, comment = '') {
  return (await client.post(`/aftersale/confirm/${reviewId}`, { action, comment })).data
}

export async function listUnresolved(limit = 50): Promise<{ count: number; items: UnresolvedItem[] }> {
  return (await client.get('/console/unresolved', { params: { limit } })).data
}

export async function resolveUnresolved(id: number) {
  return (await client.post(`/console/unresolved/${id}/resolve`)).data
}

export async function getOverview(): Promise<OverviewData> {
  return (await client.get('/console/overview')).data
}