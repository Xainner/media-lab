import {expect,test} from 'vitest'
import {render,screen} from '@testing-library/react'
import {SemanticData} from './studio/components/SemanticData'
test('structured tool arguments show labelled values, exact prompts and no secrets or JSON delimiters',()=>{
 const prompt='Una ciudad\ncon estrellas y "luz violeta"'
 const {container}=render(<SemanticData value={JSON.stringify({prompt,steps:40,secret:'hidden-fixture',analysis:{duration:12,sections:[{start:0,end:12}]}})}/>)
 expect(screen.getByText('Prompt')).toBeTruthy()
 expect(container.textContent).toContain(prompt)
 expect(container.textContent).not.toContain('hidden-fixture')
 expect(container.textContent).not.toContain('{')
 expect(screen.getByText('Duración')).toBeTruthy()
})
test('a prompt that happens to contain JSON remains verbatim text',()=>{
 const prompt='{"subject":"Rinari", "lighting":"violeta"}'
 const {container}=render(<SemanticData value={{prompt}}/>)
 expect(container.querySelector('.semantic-text')?.textContent).toBe(prompt)
})
