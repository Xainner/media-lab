import {afterEach,expect,test,vi} from 'vitest'
import {cleanup,render,screen} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {MemoryRouter} from 'react-router-dom'
import Studio from './Studio'
vi.mock('./bridge',()=>({api:async(_method:string,route:string)=>route==='/v1/health'?{status:'ok'}:{items:[]}}))
afterEach(()=>{cleanup();vi.unstubAllGlobals();localStorage.clear()})
test('the real creation prompt survives navigation to another tool and back',async()=>{
 vi.stubGlobal('matchMedia',()=>({matches:false,addEventListener(){},removeEventListener(){}}))
 vi.stubGlobal('ResizeObserver',class{observe(){} unobserve(){} disconnect(){}})
 window.scrollTo=()=>{}
 window.visualLab={platform:'web',runtime:{request:async()=>({})}} as any
 const user=userEvent.setup()
 render(<MemoryRouter initialEntries={['/advanced/image']} future={{v7_startTransition:true,v7_relativeSplatPath:true}}><Studio current={{username:'creator',user_id:'one',role:'member'}} refresh={async()=>{}} logout={async()=>{}}/></MemoryRouter>)
 await user.type(screen.getByLabelText('DESCRIPCIÓN'),'Un jardín de estrellas violetas')
 await user.click(screen.getByRole('button',{name:'Menú de la cuenta'}))
 expect(screen.queryByRole('link',{name:'Usuarios',exact:true})).toBeNull()
 await user.click(screen.getByRole('link',{name:'Música avanzada',exact:true}))
 expect(screen.getByRole('heading',{name:'Encuentra tu próximo sonido.'})).toBeTruthy()
 await user.click(screen.getByRole('button',{name:'Menú de la cuenta'}))
 await user.click(screen.getByRole('link',{name:'Imagen avanzada',exact:true}))
 expect((screen.getByLabelText('DESCRIPCIÓN') as HTMLTextAreaElement).value).toBe('Un jardín de estrellas violetas')
})
