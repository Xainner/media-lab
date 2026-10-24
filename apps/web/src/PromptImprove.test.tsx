import {afterEach,expect,test,vi} from 'vitest'
import {cleanup,render,screen} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {clearBrowser,setSession} from './bridge'
import VideoView from './studio/views/VideoView'
import MusicView from './studio/views/MusicView'
afterEach(()=>{cleanup();clearBrowser();vi.unstubAllGlobals();localStorage.clear()})
function backend(improve:(body:any)=>Response){
 const calls:any[]=[]
 vi.stubGlobal('fetch',vi.fn(async(route:string,init:RequestInit)=>{
  if(route==='/v1/agent/improve'){const body=JSON.parse(String(init.body));calls.push(body);return improve(body)}
  if(route.startsWith('/v1/jobs'))throw new Error('generation must not start')
  return new Response('{}')
 }))
 setSession({csrf:'fixture-csrf'})
 return calls
}
test('Vídeo web envía modo y segundos a /v1/agent/improve y aplica la propuesta revisada',async()=>{
 const calls=backend(()=>new Response(JSON.stringify({prompt:'scene: lanterns drift\naudio: wind'})))
 const user=userEvent.setup()
 render(<VideoView/>)
 const input=screen.getByLabelText('Dirección visual') as HTMLTextAreaElement
 await user.type(input,'Linternas sobre el lago')
 await user.click(screen.getByRole('button',{name:'PROPONER MEJORA EXTERNA'}))
 expect(await screen.findByText(/scene: lanterns drift/)).toBeTruthy()
 expect(calls).toEqual([{prompt:'Linternas sobre el lago',mode:'t2v',references:[],seconds:5}])
 expect(input.value).toBe('Linternas sobre el lago')
 await user.click(screen.getByRole('button',{name:'ACEPTAR ESTA PROPUESTA'}))
 expect(input.value).toBe('scene: lanterns drift\naudio: wind')
})
test('Música web rellena estilo y letra y muestra en español los fallos del proveedor',async()=>{
 let fail=true
 const calls=backend(()=>fail?new Response('{"detail":"Proveedor no configurado"}',{status:400}):new Response(JSON.stringify({prompt:'folk, acoustic guitar',lyrics:'[Verse]\nCamino'})))
 const user=userEvent.setup()
 render(<MusicView/>)
 await user.type(screen.getByLabelText('Estilo'),'folk íntimo')
 await user.click(screen.getByRole('button',{name:'PROPONER MEJORA EXTERNA'}))
 expect(await screen.findByText('Proveedor externo: Runtime 400: Proveedor no configurado')).toBeTruthy()
 fail=false
 await user.click(screen.getByRole('button',{name:'PROPONER MEJORA EXTERNA'}))
 await user.click(await screen.findByRole('button',{name:'ACEPTAR ESTA PROPUESTA'}))
 expect(calls.at(-1)).toEqual({prompt:'Style: folk íntimo',mode:'song',references:[]})
 expect((screen.getByLabelText('Estilo') as HTMLTextAreaElement).value).toBe('folk, acoustic guitar')
 expect((screen.getByLabelText('Letra') as HTMLTextAreaElement).value).toBe('[Verse]\nCamino')
})
