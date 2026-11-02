import request from '@/utils/request'
import type { ModelItem } from '@/store/modelStore'
interface CallOpts { silent?: boolean }
const cfg = (o?: CallOpts) => o?.silent ? {suppressToast: true} : undefined
export const updateProviderById = (data: any, opts?: CallOpts) => request.post<unknown, any>('/update_provider', data, cfg(opts))
export const addProvider = (data: any, opts?: CallOpts) => request.post<unknown, any>('/add_provider', data, cfg(opts))
export const addModel = (data: {provider_id: string; model_name: string}, opts?: CallOpts) => request.post<unknown, any>('/models', data, cfg(opts))
export const fetchEnableModels = () => request.get<unknown, ModelItem[]>('/model_list')
