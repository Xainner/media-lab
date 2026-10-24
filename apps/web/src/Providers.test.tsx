import {afterEach,beforeEach,expect,test,vi} from 'vitest'
import {cleanup,render,screen,waitFor} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {MemoryRouter} from 'react-router-dom'
import Providers from './Providers'
const api=vi.hoisted(()=>vi.fn())
vi.mock('./bridge',()=>({api}))
vi.mock('./ui',()=>({Notice:({error,success}:any)=><p>{error||success}</p>,Modal:({open,title,children}:any)=>open?<section aria-label={title}>{children}</section>:null}))
beforeEach(()=>{
 window.visualLab={agent:{onEvent:()=>()=>{}}} as any
 api.mockImplementation(async(method,route)=>{
  if(route==='/v1/account/endpoints')return {items:[{id:'one',label:'Mi proveedor'}]}
  if(route==='/v1/account/providers')return {items:[{endpoint_id:'one',model:'',enabled:true}],active:{configured:false}}
  if(route==='/v1/agent/runs')return []
  if(route.endsWith('/models'))return {items:[{id:'first'},{id:'second'}]}
  return {ok:true}
 })
})
afterEach(()=>{cleanup();api.mockReset()})
test('discovers a saved key before choosing a model, searches and activates the explicit choice',async()=>{
 const user=userEvent.setup();render(<MemoryRouter future={{v7_startTransition:true,v7_relativeSplatPath:true}}><Providers/></MemoryRouter>)
 await screen.findByRole('option',{name:'second'})
 await user.type(screen.getByLabelText('Buscar modelos'),'second')
 expect(screen.queryByRole('option',{name:'first'})).toBeNull()
 await user.selectOptions(screen.getAllByRole('combobox')[1],'second')
 await user.click(screen.getByRole('button',{name:'Usar este modelo'}))
 await waitFor(()=>expect(api).toHaveBeenCalledWith('POST','/v1/account/providers/activate',{endpoint_id:'one',model:'second'}))
})
test('unavailable discovery permits a manual identifier with a comprehensible error',async()=>{
 const original=api.getMockImplementation()!
 api.mockImplementation((method,route,...rest)=>route.endsWith('/models')?Promise.reject(new Error('Catálogo no disponible')):original(method,route,...rest))
 const user=userEvent.setup();render(<MemoryRouter future={{v7_startTransition:true,v7_relativeSplatPath:true}}><Providers/></MemoryRouter>)
 await screen.findByText(/No pudimos obtener el catálogo/)
 await user.type(screen.getByPlaceholderText('Identificador del modelo'),'manual-model')
 await user.click(screen.getByRole('button',{name:'Usar este modelo'}))
 await waitFor(()=>expect(api).toHaveBeenCalledWith('POST','/v1/account/providers/activate',{endpoint_id:'one',model:'manual-model'}))
})
test('running agent locks selection and key replacement',async()=>{
 const original=api.getMockImplementation()!
 api.mockImplementation((method,route,...rest)=>route==='/v1/agent/runs'?Promise.resolve([{status:'running'}]):original(method,route,...rest))
 render(<MemoryRouter future={{v7_startTransition:true,v7_relativeSplatPath:true}}><Providers/></MemoryRouter>)
 await screen.findByText(/El agente está trabajando/)
 expect((screen.getByRole('button',{name:'Usar este modelo'}) as HTMLButtonElement).disabled).toBe(true)
 expect((screen.getByLabelText('Clave API') as HTMLInputElement).disabled).toBe(true)
})
test('a disabled provider remains visible so the owner can retire its saved connection',async()=>{
 const original=api.getMockImplementation()!
 api.mockImplementation((method,route,...rest)=>route==='/v1/account/providers'?Promise.resolve({items:[{endpoint_id:'retired',label:'Proveedor retirado',model:'old-model',enabled:false}],active:{configured:false}}):original(method,route,...rest))
 const user=userEvent.setup();render(<MemoryRouter future={{v7_startTransition:true,v7_relativeSplatPath:true}}><Providers/></MemoryRouter>)
 await user.click(await screen.findByRole('button',{name:/Proveedor retirado/}))
 await screen.findByText(/Este proveedor está desactivado/)
 expect((screen.getByRole('button',{name:'Guardar conexión'}) as HTMLButtonElement).disabled).toBe(true)
 expect((screen.getByRole('button',{name:'Retirar mi conexión'}) as HTMLButtonElement).disabled).toBe(false)
})

test('new accounts choose explicitly and can add a personal endpoint before saving a key',async()=>{
 const original=api.getMockImplementation()!
 let added=false,configured=false
 api.mockImplementation((method,route,...rest)=>{
  if(route==='/v1/account/endpoints'&&method==='POST'){added=true;return Promise.resolve({id:'personal',label:'Mi IA',base_url:'https://api.example/v1',personal:true})}
  if(route==='/v1/account/endpoints')return Promise.resolve({items:[{id:'one',label:'Equipo'},...(added?[{id:'personal',label:'Mi IA',base_url:'https://api.example/v1',personal:true}]:[])]})
  if(route==='/v1/account/providers/personal'&&method==='PUT'){configured=true;return Promise.resolve({ok:true})}
  if(route==='/v1/account/providers')return Promise.resolve({items:configured?[{endpoint_id:'personal',label:'Mi IA',enabled:true,model:'',personal:true}]:[],active:{configured:false,endpoint_id:''}})
  return original(method,route,...rest)
 })
 const user=userEvent.setup();render(<MemoryRouter future={{v7_startTransition:true,v7_relativeSplatPath:true}}><Providers/></MemoryRouter>)
 await screen.findByRole('option',{name:'Equipo'})
 expect((screen.getByLabelText('Proveedor') as HTMLSelectElement).value).toBe('')
 expect((screen.getByLabelText('Clave API') as HTMLInputElement).disabled).toBe(true)
 await user.click(screen.getByRole('button',{name:'Añadir proveedor'}))
 await user.type(screen.getByLabelText('Nombre del proveedor'),'Mi IA')
 await user.type(screen.getByLabelText('URL de la API'),'https://api.example/v1')
 await user.click(screen.getByRole('button',{name:'Añadir a mi cuenta'}))
 await screen.findByRole('heading',{name:'Mi IA'})
 expect(api).toHaveBeenCalledWith('POST','/v1/account/endpoints',{label:'Mi IA',base_url:'https://api.example/v1'})
 await user.type(screen.getByLabelText('Clave API'),'my-private-key')
 await user.click(screen.getByRole('button',{name:'Guardar conexión'}))
 await screen.findByRole('option',{name:'second'})
 expect(api).toHaveBeenCalledWith('PUT','/v1/account/providers/personal',{model:'',api_key:'my-private-key'})
 await user.selectOptions(screen.getByRole('combobox',{name:'Modelo'}),'second')
 await user.click(screen.getByRole('button',{name:'Usar este modelo'}))
 await waitFor(()=>expect(api).toHaveBeenCalledWith('POST','/v1/account/providers/activate',{endpoint_id:'personal',model:'second'}))
})
