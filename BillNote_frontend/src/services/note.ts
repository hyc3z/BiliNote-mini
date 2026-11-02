import request from '@/utils/request'
import type { Task, TaskStatus } from '@/store/taskStore'
interface TaskResponse { status: TaskStatus; message?: string; progress?: Record<string, any>; partial_result?: {transcript?: Task['transcript']; audio_meta?: Task['audioMeta']}; result: {markdown: string; transcript: Task['transcript']; audio_meta: Task['audioMeta']; summary_stale?: boolean} }
export const generateNote = (data: Record<string, any>) => request.post<unknown, {task_id: string}>('/generate_note', data)
export const get_task_status = (id: string, includeTranscript = true) => request.get<unknown, TaskResponse>('/task_status/' + id, { params: { include_transcript: includeTranscript } })
