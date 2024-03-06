from django.shortcuts import render, redirect, get_object_or_404
from django.db import connection
from .models import ShowTable, Movie, TvSeries, History, Watchlist, WatchlistShow
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
import ast
from django.contrib.auth.decorators import login_required


def register_user(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            success_url = reverse("index")
            return HttpResponseRedirect(success_url)
    else:
        form = UserCreationForm()

    context = {"form": form}

    return render(request, "registration/registration_form.html", context)


@login_required(login_url="/login/")
def home_page(request):
    user_id = request.user.id

    # Using raw queries as syntax for Django ORM is new to me
    new_release_columns = ['Show_ID', 'Show_Name', 'Show_Description', 'Show_Type']
    new_release_query = """
        SELECT 
            st.Show_ID as Show_ID,
            unioned.Show_Name as Show_Name,
            unioned.Show_Description as Show_Description,
            unioned.Show_Type as Show_Type,
            unioned.Show_Release_Date as Show_Release_Date
        FROM
            (
                (SELECT
                    Movie_ID AS Show_ID,
                    Name AS Show_Name,
                    Description as Show_Description,
                    'Movie' AS Show_Type,
                    Release_Date AS Show_Release_Date
                FROM
                    Movie)

                UNION ALL

                (SELECT
                    TV_Series_ID AS Show_ID,
                    Name AS Show_Name,
                    Description as Show_Description,
                    'TV' AS Show_Type,
                    Release_Date AS Show_Release_Date
                FROM
                    TV_Series)
            ) AS unioned
        JOIN
            Show_Table st ON 
            (st.Movie_ID = unioned.Show_ID)
            OR 
            (st.TV_Series_ID = unioned.Show_ID)
        ORDER BY 
            Show_Release_Date DESC 
        LIMIT 10;
    """

    with connection.cursor() as cursor:
        cursor.execute(new_release_query)
        new_release_shows = cursor.fetchall()
        new_release_shows = [
            # exclude release date
            {new_release_columns[i]: value for i, value in enumerate(show[:-1])} for show in new_release_shows
        ]
    top_rated_show = get_top_rated_movies(request)

    context = {
        'card_count': range(10),
        'user_id': user_id,
        'new_release_shows': new_release_shows,
        'top_rated_show': top_rated_show
    }
    return render(request, "home.html", context)


# Create a pop up alert for no search result
@login_required(login_url="/login/")
def search_feature(request):
    if request.method == 'POST':
        search_query = request.POST.get('search_query', '')

        try:
            movie = Movie.objects.get(name__icontains=search_query)
            show_table = ShowTable.objects.get(movie_id=movie.movie_id)
            show_id = show_table.show_id
            return show_page(request, show_id)
        except Movie.DoesNotExist:
            pass

        try:
            tv_series = TvSeries.objects.get(name__icontains=search_query)
            show_table = ShowTable.objects.get(tv_series_id=tv_series.tv_series_id)
            show_id = show_table.show_id
            return show_page(request, show_id)
        except TvSeries.DoesNotExist:
            context = {'error_message': 'No search result, please check again'}
    return render(request, 'post_search.html', context)


@login_required(login_url="/login/")
def show_page(request, show_id):
    user_id = request.user.id

    ### Show data ###
    show = get_object_or_404(ShowTable, pk=show_id)
    if show.movie_id:
        show = get_object_or_404(Movie, pk=show.movie_id)
        show_type = "Movie"
    else:
        show = get_object_or_404(TvSeries, pk=show.tv_series_id)
        show_type = "TV"
    show_genres_set = set(ast.literal_eval(show.genre))

    ### Similar movies or shows ###

    movies = Movie.objects.all()
    tv_shows = TvSeries.objects.all()
    movies_common = [movie for movie in movies if len(set(ast.literal_eval(movie.genre)) & show_genres_set) >= 2][:5]
    tv_shows_common = [tv_show for tv_show in tv_shows if len(set(ast.literal_eval(tv_show.genre)) & show_genres_set) >= 2][:5]
    similar_shows = movies_common + tv_shows_common
    similar_shows = sorted(similar_shows, key=lambda x: x.release_date)
    ### Reviews ###
    reviews = History.objects.filter(show_id=show_id).select_related('user_id').order_by('-review_date')[:5]

    ### Status distribution ###
    status_types = ['Planned', 'Watching', 'Completed', 'Dropped']
    # pass in show_id as parameter when executing query rather than string interpolation to prevent sql injection
    status_distribution_query = """
        SELECT
            Status, COUNT(*) as Count
        FROM
            WatchlistShow
        WHERE
            Show_ID = %s
        GROUP BY Status;
    """
    # if status is not in the query results, count should be 0, so init an empty dict first
    status_distribution = {status_type: 0 for status_type in status_types}

    ### Execute queries ###
    with connection.cursor() as cursor:
        cursor.execute(status_distribution_query, [show_id])
        for row in cursor.fetchall():
            status_distribution[row[0]] = row[1]

    ### Build context and return
    context = {
        'show': show,
        'show_type': show_type,
        'status_distribution': status_distribution,
        'reviews': reviews,
        'card_count': range(10),
        'user_id': user_id,
        'similar_shows': similar_shows
    }

    return render(request, "show.html", context)


@login_required(login_url="/login/")
def my_list_page(request):
    user_id = request.user.id
    watchlist_id = Watchlist.objects.get(user_id=user_id).watchlist_id
    watchlist_show = WatchlistShow.objects.filter(watchlist_id=watchlist_id).select_related('show_id')

    shows = []
    for show in watchlist_show:
        if show.show_id.movie_id:
            show = get_object_or_404(Movie, pk=show.show_id.movie_id)
            show.type = "Movie"
        else:
            show = get_object_or_404(TvSeries, pk=show.show_id.tv_series_id)
            show.type = "TV"
        show.genre = ', '.join(ast.literal_eval(show.genre))
        shows.append(show)

    context = {
        'shows': shows,
        'card_count': range(10),
        'user_id': user_id
    }
    return render(request, "my_list.html", context)

def get_top_rated_movies(request):
    top_histories = History.objects.filter(rating=5).order_by('-review_date')[:10]
    top_rated_shows = []

    for history in top_histories:
        try:
            show = history.show_id

            if show.movie_id is not None:
                movie = Movie.objects.get(movie_id=show.movie_id)
                top_rated_shows.append({'name': movie.name, 'description': movie.description})

            elif show.tv_series_id is not None:
                series = TvSeries.objects.get(tv_series_id=show.tv_series_id)
                top_rated_shows.append({'name': series.name, 'description': series.description})

        except ShowTable.DoesNotExist:
            pass

    return top_rated_shows
