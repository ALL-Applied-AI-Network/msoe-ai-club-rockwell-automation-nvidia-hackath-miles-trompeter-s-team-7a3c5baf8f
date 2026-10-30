import unittest
from unittest.mock import patch
from run_chat import ask, snapshot

def row(vial,status='complete',finding='appearance deviation - review'):
    return dict(id=f'job-{vial}',number=vial,seconds=vial,recipe=dict(vial=vial,recipe_id=5),status=status,color=dict(status=finding),image='PRIVATE_IMAGE')

class RunChatTests(unittest.TestCase):
    def test_unique_counts_and_multiple_flags(self):
        a=row(1); a['fill']={'status':'possible low fill - review'}
        facts=snapshot([a,a,row(2,'running','insufficient evidence'),row(3,'error','insufficient evidence')])
        self.assertEqual(facts['total'],3)
        self.assertEqual(facts['counts'],dict(review=1,uncertain=1,pending=1,no_clear_deviation=0))
        self.assertNotIn('PRIVATE_IMAGE',str(facts))
    def test_count_questions_never_call_model(self):
        with patch('run_chat.requests.post') as post:
            answer=ask('How many vials need checking?',[row(1)])
            self.assertIn('1 unique',answer['answer'])
            self.assertEqual(answer['source'],'run data')
            post.assert_not_called()
    def test_reference_is_not_pass(self):
        a=row(3,finding='no clear appearance deviation')
        a['sequence']={'third_vial_comparison':{'decision':'reference only - not scored'}}
        self.assertEqual(snapshot([a])['counts']['uncertain'],1)
    def test_failure_preserves_counts(self):
        with patch('run_chat.load_dotenv'),patch.dict('os.environ',{'COSMOS_API_KEY':''}):
            result=ask('Explain vial 1',[row(1)])
            self.assertEqual(result['source'],'unavailable')
            self.assertEqual(result['snapshot']['counts']['review'],1)
    def test_cosmos_receives_only_bounded_text_facts(self):
        with patch('run_chat.load_dotenv'),patch.dict('os.environ',{'COSMOS_BASE_URL':'http://localhost:8001/v1','COSMOS_API_KEY':'test'}),patch('run_chat.requests.post') as post:
            post.return_value.status_code=200
            post.return_value.json.return_value={'choices':[{'finish_reason':'stop','message':{'content':'Recorded deviation requires review.'}}]}
            result=ask('Explain vial 1',[row(1)])
            self.assertIn('Cosmos',result['source'])
            self.assertNotIn('PRIVATE_IMAGE',str(post.call_args.kwargs['json']))
    def test_empty_run(self):
        self.assertIn('No captures',ask('Explain this run',[])['answer'])

if __name__=='__main__': unittest.main()
