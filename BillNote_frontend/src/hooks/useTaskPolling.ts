import { useEffect, useRef } from 'react'
import { useTaskStore } from '@/store/taskStore'
import { get_task_status } from '@/services/note.ts'
import toast from 'react-hot-toast'

export const useTaskPolling = (interval = 3000) => {
  const tasks = useTaskStore(state => state.tasks)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)

  const finalCheckedRef = useRef(new Set<string>())
  const tasksRef = useRef(tasks)

  // 每次 tasks 更新，把最新的 tasks 同步进去
  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  useEffect(() => {
    let polling=false, cursor=0
    const timer = setInterval(async () => {
      if(polling)return
      polling=true
      let completed=0
      try {
      const pendingTasks = tasksRef.current.filter(
        task => (task.status !== 'SUCCESS' && task.status !== 'FAILED') || (task.status==='FAILED' && task.message==='上次处理被中断，已保留缓存，可以重试。' && !finalCheckedRef.current.has(task.id))
      )

      // 无活跃任务时跳过轮询
      if (pendingTasks.length === 0) return

      const selected=[...pendingTasks.slice(cursor),...pendingTasks.slice(0,cursor)].slice(0,30)
      cursor=(cursor+30)%pendingTasks.length
      for (const task of selected) {
        try {
          const res = await get_task_status(task.id, !task.transcript?.segments?.length)
          const partial: any = {}
          if (res.partial_result?.transcript) partial.transcript = res.partial_result.transcript
          if (res.partial_result?.audio_meta) partial.audioMeta = res.partial_result.audio_meta
          if (res.status === 'FAILED' || res.status === 'SUCCESS') finalCheckedRef.current.add(task.id)
          const { status } = res

          if (status) {
            if (status === 'SUCCESS') {
              const { markdown, transcript, audio_meta } = res.result
              completed++
              updateTaskContent(task.id, {
                status,
                markdown,
                transcript,
                audioMeta: audio_meta,
                summaryStale: !!res.result.summary_stale,
                progress: res.progress,
                message: res.message,
              })
            } else if (status === 'FAILED') {
              updateTaskContent(task.id, { status, message: res.message, progress: res.progress, ...partial } as any)
              console.warn(`⚠️ 任务 ${task.id} 失败`)
            } else {
              updateTaskContent(task.id, { status, message: res.message, progress: res.progress, ...partial } as any)
            }
          }
        } catch (e) {
          console.error('❌ 任务轮询失败：', e)
          // Keep the task active across temporary network failures.
        }
      }
      } finally {polling=false;if(completed)toast.success('本轮完成 '+completed+' 条笔记，进度已更新',{id:'batch-completion',duration:2500})}
    }, interval)

    return () => clearInterval(timer)
  }, [interval])
}

