import { apiRequest, apiUploadFormData } from "@/api/client";
import type { OrderBlankStatusDto, OrderBlankUploadResponseDto } from "@/api/types";

export const orderBlankApi = {
  status(): Promise<OrderBlankStatusDto> {
    return apiRequest<OrderBlankStatusDto>("/api/v1/order-blank/status");
  },

  upload(file: File, signal?: AbortSignal): Promise<OrderBlankUploadResponseDto> {
    const body = new FormData();
    body.append("file", file);
    return apiUploadFormData<OrderBlankUploadResponseDto>(
      "/api/v1/order-blank/upload",
      body,
      { signal },
    );
  },
};
