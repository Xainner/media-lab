import {afterEach,expect,test,vi} from 'vitest'
import {cleanup,render,screen,waitFor} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {clearBrowser,setSession} from './bridge'
import CreateView from './studio/views/CreateView'
import UpscalePanel from './studio/components/Upscale'
import {variantOptions} from './studio/components/ImageModel'
afterEach(()=>{cleanup();clearBrowser();vi.unstubAllGlobals();localStorage.clear()})

const caps=(turbo:boolean)=>({model_precisions:{int8:true,bf16:false},resolution_presets:[],
 model_variants:{base:{precisions:{int8:true,bf16:false}},turbo:{precisions:{int8:turbo,bf16:false}}},
 upscale:{ready:true,max_seconds:600,max_input_pixels:{'2':1100000,'4':420000}}})
function backend(turbo=true){
 const posts:{route:string,body:any}[]=[]
 vi.stubGlobal('fetch',vi.fn(async(route:string,init:RequestInit={})=>{
  if(route==='/v1/capabilities')return new Response(JSON.stringify(caps(turbo)))
  if(init.method==='POST'&&route.startsWith('/v1/jobs/')){posts.push({route,body:JSON.parse(String(init.body))});return new Response(JSON.stringify({job_id:'job_1',status:'queued'}),{status:202})}
  if(route.startsWith('/v1/jobs/job_1'))return new Response(JSON.stringify({id:'job_1',status:'failed',operation:'generate',activity:[],error:'fixture'}))
  return new Response('{}')
 }))
 setSession({csrf:'fixture-csrf'})
 return posts
}

test('Turbo drops the fixed-schedule options and keeps the rest',()=>{
 expect(variantOptions('turbo',{steps:20,scheduler:'karras',denoise:.5,cfg:2,negative_prompt:'x'})).toEqual({cfg:2,negative_prompt:'x'})
 expect(variantOptions('turbo',{steps:20})).toBeUndefined()
 expect(variantOptions('base',{steps:20})).toEqual({steps:20})
})

test('Crear con Turbo envía model_variant, oculta la calidad por pasos y recuerda la elección',async()=>{
 const posts=backend(true)
 const user=userEvent.setup()
 render(<CreateView active/>)
 const turbo=await screen.findByRole('button',{name:/Turbo/})
 expect(screen.getByLabelText('Calidad de generación')).toBeTruthy()
 await user.click(turbo)
 expect(screen.queryByLabelText('Calidad de generación')).toBeNull()
 expect(localStorage.getItem('media-lab:image-variant')).toBe('turbo')
 await user.type(screen.getByLabelText('DESCRIPCIÓN'),'Un café nocturno')
 await user.click(screen.getByRole('button',{name:'GENERAR'}))
 await waitFor(()=>expect(posts.length).toBe(1))
 expect(posts[0].route).toBe('/v1/jobs/generate')
 expect(posts[0].body).toMatchObject({prompt:'Un café nocturno',model_variant:'turbo',model_precision:'int8'})
})

test('sin pesos Turbo instalados no aparece el selector y se usa Qwen 2.1',async()=>{
 localStorage.setItem('media-lab:image-variant','turbo')
 const posts=backend(false)
 const user=userEvent.setup()
 render(<CreateView active/>)
 await user.type(screen.getByLabelText('DESCRIPCIÓN'),'Un faro')
 await waitFor(()=>expect(screen.getByLabelText('Calidad de generación')).toBeTruthy())
 expect(screen.queryByRole('button',{name:/Turbo/})).toBeNull()
 await user.click(screen.getByRole('button',{name:'GENERAR'}))
 await waitFor(()=>expect(posts.length).toBe(1))
 expect(posts[0].body.model_variant).toBe('base')
})

test('el panel de escalado bloquea x4 en vídeos grandes y envía x2 rápido',async()=>{
 const posts=backend()
 const user=userEvent.setup()
 render(<UpscalePanel media={{uri:'artifact://s/videos/a.mp4',sha256:'a'.repeat(64),width:1280,height:704}}/>)
 const x4=await screen.findByRole('button',{name:/^x4/})
 expect((x4 as HTMLButtonElement).disabled).toBe(true)
 expect(screen.getByRole('button',{name:/^x2/}).getAttribute('aria-pressed')).toBe('true')
 await user.click(screen.getByRole('button',{name:'ESCALAR x2'}))
 await waitFor(()=>expect(posts.length).toBe(1))
 expect(posts[0]).toEqual({route:'/v1/jobs/upscale',body:{video:{uri:'artifact://s/videos/a.mp4',sha256:'a'.repeat(64)},scale:2,quality:'fast'}})
})

test('el panel de escalado no aparece para imágenes',async()=>{
 backend()
 const {container}=render(<UpscalePanel media={{uri:'artifact://s/images/a.png',sha256:'a'.repeat(64)}}/>)
 await new Promise(r=>setTimeout(r,20))
 expect(container.querySelector('.upscale-panel')).toBeNull()
})
