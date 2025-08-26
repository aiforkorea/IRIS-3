$(function(){
    // 미매칭 사용자 목록 가져오기
    function load_unmatched(q=''){
        $.get('/admin/match', { ajax:'unmatched_users'}, function(data){
            let lst=$("#unmatched_users_list").empty();
            data.forEach(function(u){
                if(q=='' || u.email.indexOf(q)!==-1 || String(u.id)==q)
                    lst.append(`<li class="list-group-item"><input type="checkbox" value="${u.id}" class="userids"> ${u.id} ${u.email}</li>`);
            });
        });
    }
    $("#user_search").on('input', function(){ load_unmatched(this.value); });
    load_unmatched();

    // 매칭 생성
    $("#create_match_btn").click(function(){
        let user_ids = [];
        $(".userids:checked").each(function(){
            user_ids.push($(this).val());
        });
        let expert_id = $("#assign_expert").val();
        if(user_ids.length==0 || !expert_id){
            $("#createmsg").html('<span class="text-danger">사용자/전문가 선택 필요!</span>');
            return;
        }
        $.post('/admin/match/create', { user_ids:user_ids, expert_id:expert_id }, function(resp){
            $("#createmsg").html('<span class="text-success">'+resp.created+'건 매칭 생성 완료!</span>');
            load_unmatched();
        });
    });

    // 전체 선택 체크박스
    $("#chkall").change(function(){
        $("input[name='selected_matches']").prop('checked', $(this).prop('checked'));
    });
});
