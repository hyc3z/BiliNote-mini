import { create } from 'zustand'
import { fetchEnableModels } from '@/services/model'
export interface ModelItem { id: string; provider_id: string; model_name: string }
export const useModelStore = create<{modelList: ModelItem[]; loadEnabledModels: () => Promise<void>}>((set) => ({
 modelList: [],
 loadEnabledModels: async () => { try { set({modelList: await fetchEnableModels()}) } catch { set({modelList: []}) } },
}))
