import { fetchJson } from './client'
import type { components } from './generated/schema'

export type TokenResponse = components['schemas']['TokenResponse']
export type UserOut = components['schemas']['UserOut']
export type Body_login_auth_login_post = components['schemas']['Body_login_auth_login_post']
export type UserRegister = components['schemas']['UserRegister']

export const authApi = {
  async login(data: Body_login_auth_login_post): Promise<TokenResponse> {
    const formData = new URLSearchParams()
    formData.append('username', data.username)
    formData.append('password', data.password)
    if (data.scope) formData.append('scope', data.scope)
    
    return fetchJson<TokenResponse>('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: formData.toString()
    })
  },
  
  async register(data: UserRegister): Promise<UserOut> {
    return fetchJson<UserOut>('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
  },
  
  async getMe(): Promise<UserOut> {
    return fetchJson<UserOut>('/auth/me')
  }
}
