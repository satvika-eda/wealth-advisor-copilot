import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
});

// Chat API
export const chatApi = {
  sendMessage: async (message, conversationId = null, clientId = null, docTypes = null, companyFilter = null) => {
    const response = await api.post('/chat/', {
      message,
      conversation_id: conversationId,
      client_id: clientId,
      doc_types: docTypes,
      company_filter: companyFilter,
    });
    return response.data;
  },
  
  getConversations: async (limit = 50) => {
    const response = await api.get('/chat/conversations', { params: { limit } });
    return response.data;
  },
};

// Documents API
export const documentsApi = {
  list: async (page = 1, perPage = 20) => {
    const response = await api.get('/documents/', { params: { page, per_page: perPage } });
    return response.data;
  },
  
  upload: async (file, title, clientId, companyName) => {
    const formData = new FormData();
    formData.append('file', file);
    if (title) formData.append('title', title);
    if (clientId) formData.append('client_id', clientId);
    if (companyName) formData.append('company_name', companyName);
    
    const response = await api.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
  
  ingestEdgar: async (cik, filingType, accessionNumber, clientId) => {
    const response = await api.post('/documents/edgar', {
      cik,
      filing_type: filingType,
      accession_number: accessionNumber,
      client_id: clientId,
    });
    return response.data;
  },
  
  delete: async (documentId) => {
    const response = await api.delete(`/documents/${documentId}`);
    return response.data;
  },
};

// Admin API
export const adminApi = {
  getAuditLogs: async (page = 1, perPage = 50, filters = {}) => {
    const response = await api.get('/admin/audit-logs', {
      params: { page, per_page: perPage, ...filters },
    });
    return response.data;
  },
  
  getAuditLog: async (logId) => {
    const response = await api.get(`/admin/audit-logs/${logId}`);
    return response.data;
  },
  
  getStats: async (days = 7) => {
    const response = await api.get('/admin/stats', { params: { days } });
    return response.data;
  },
};

export default api;
