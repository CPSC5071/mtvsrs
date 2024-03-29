from ast import literal_eval
from collections import defaultdict
from datetime import date

import numpy as np
import plotly.express as px
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST
from .forms import CustomUserCreationForm, ReviewForm
from .models import ShowTable, Movie, TvSeries, History, Watchlist, WatchlistShow, User


def register_user(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            success_url = reverse("login")
            return HttpResponseRedirect(success_url)
    else:
        form = CustomUserCreationForm()

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

    trending_shows = get_trending_shows(request)
    recommend_shows = recommend_similar_shows(user_id)

    context = {
        'card_count': range(10),
        'user_id': user_id,
        'new_release_shows': new_release_shows,
        'trending_shows': trending_shows,
        'recommend_shows': recommend_shows
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
    watchlist_id = Watchlist.objects.get(user_id=user_id).watchlist_id
    try:
        current_status = WatchlistShow.objects.get(watchlist_id=watchlist_id, show_id=show_id).status
    except WatchlistShow.DoesNotExist:
        current_status = None

    ### Show data ###
    show = get_object_or_404(ShowTable, pk=show_id)
    if show.movie_id:
        show = get_object_or_404(Movie, pk=show.movie_id)
        show_type = "Movie"
    else:
        show = get_object_or_404(TvSeries, pk=show.tv_series_id)
        show_type = "TV"
    # parse genre string into list, then concat them with just a comma
    literal_eval_genre = literal_eval(show.genre)
    show.genre = ', '.join(literal_eval_genre)

    ### Similar shows ##
    show_genres_set = set(literal_eval_genre)
    movies = Movie.objects.all()
    tv_shows = TvSeries.objects.all()
    movies_common = [movie for movie in movies if len(set(literal_eval(movie.genre)) & show_genres_set) >= 2][:5]
    tv_shows_common = [tv_show for tv_show in tv_shows if
                       len(set(literal_eval(tv_show.genre)) & show_genres_set) >= 2][:5]
    similar_shows = movies_common + tv_shows_common
    similar_shows = sorted(similar_shows, key=lambda x: x.release_date)
    # use movie.movie_id or tv_series.tv_series_id to get the show_id
    for similar_show in similar_shows:
        movie_id = getattr(similar_show, 'movie_id', None)
        tv_series_id = getattr(similar_show, 'tv_series_id', None)
        if movie_id:
            similar_show.show_id = ShowTable.objects.get(movie_id=movie_id).show_id
            similar_show.show_type = "Movie"
        else:
            similar_show.show_id = ShowTable.objects.get(tv_series_id=tv_series_id).show_id
            similar_show.show_type = "TV"

    ### Reviews ###
    review_count = History.objects.filter(show_id=show_id).count()
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

    ### Score distribution ###
    score_distribution_query = """
        SELECT rating FROM History WHERE Show_ID = %s;
    """
    # initialize for histogram, technically not necessary and we can use px.histogram
    # but because our data is sparse sometimes there are no counts for a rating
    score_distribution = {score: 0 for score in np.arange(1, 6)}

    ### Execute queries ###
    with (connection.cursor() as cursor):
        ### Status distribution ###
        cursor.execute(status_distribution_query, [show_id])
        for row in cursor.fetchall():
            status_distribution[row[0]] = row[1]

        ### Score distribution ###
        cursor.execute(score_distribution_query, [show_id])
        for row in cursor.fetchall():
            score_distribution[row[0]] += 1

    ### Score distribution ###
    ratings = list(score_distribution.keys())
    counts = list(score_distribution.values())
    score_distribution_plot = px.bar(
        x=ratings,
        y=counts,
        color=counts,
        color_continuous_scale=[(0, "red"), (0.5, "yellow"), (1, "green")],
        template="plotly_dark",
    )
    # remove all labels and make responsive
    score_distribution_plot.update_layout(
        xaxis_title="",
        yaxis_title="",
        title="",
        xaxis_showticklabels=True,
        yaxis_showticklabels=False,
        xaxis_visible=True,
        yaxis_visible=False,
        autosize=True,
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)",  # transparent background
        coloraxis_showscale=False,  # hide the color scale bar
        hovermode=False,
        bargap=0.4
    )
    # adjust marker properties
    score_distribution_plot.update_traces(
        marker_line_width=0,  # borders around bars
        marker_opacity=0.6,
    )
    score_distribution_plot = score_distribution_plot.to_html(full_html=False, config={'displayModeBar': False})

    ### My Review ###
    user_review = None
    try:
        user_review = History.objects.get(show_id=show_id, user_id=user_id)
    except History.DoesNotExist:
        pass
    review_form = ReviewForm()  # pass in empty form for review submission

    ### Build context and return ###
    context = {
        'show': show,  # this will not have show_id, but movie_id or tv_series_id
        'show_id': show_id,
        'show_type': show_type,
        'watchlist_id': watchlist_id,
        'current_status': current_status,
        'status_types': status_types,
        'status_distribution': status_distribution,
        'score_distribution_plot': score_distribution_plot,
        'review_count': review_count,
        'reviews': reviews,
        'card_count': range(10),
        'user_id': user_id,
        'similar_shows': similar_shows,
        'review_form': review_form,
        'user_review': user_review
    }

    return render(request, "show.html", context)


@login_required(login_url="/login/")
def my_list_page(request):
    user_id = request.user.id
    watchlist_id = Watchlist.objects.get(user_id=user_id).watchlist_id
    watchlist_shows = WatchlistShow.objects.filter(watchlist_id=watchlist_id).select_related('show_id')

    shows_by_status = defaultdict(list)
    for ws in watchlist_shows:
        if ws.show_id.movie_id:
            s = get_object_or_404(Movie, pk=ws.show_id.movie_id)
            s.show_type = "Movie"
        else:
            s = get_object_or_404(TvSeries, pk=ws.show_id.tv_series_id)
            s.show_type = "TV"
        s.genre = ', '.join(literal_eval(s.genre))
        s.show_id = ws.show_id_id
        s.status = ws.status
        shows_by_status[s.status].append(s)

    context = {
        'shows_by_status': dict(shows_by_status),  # django wont render defaultdict
        'user_id': user_id
    }

    return render(request, "my_list.html", context)


def get_trending_shows(request):
    top_histories = History.objects.filter(rating=5).order_by('-review_date')[:10]

    trending_shows = []
    for history in top_histories:
        try:
            show = history.show_id

            if show.movie_id is not None:
                movie = Movie.objects.get(movie_id=show.movie_id)
                trending_shows.append({'name': movie.name, 'description': movie.description, 'show_id': show.show_id,
                                       'show_type': 'Movie'})

            elif show.tv_series_id is not None:
                series = TvSeries.objects.get(tv_series_id=show.tv_series_id)
                trending_shows.append({'name': series.name, 'description': series.description, 'show_id': show.show_id,
                                       'show_type': 'TV'})

        except ShowTable.DoesNotExist:
            pass

    return trending_shows


@require_POST
def change_status(request):
    watchlist_id = int(request.POST.get('watchlistId'))
    show_id = int(request.POST.get('showId'))
    new_status = request.POST.get('newStatus')

    _, created = WatchlistShow.objects.filter(watchlist_id=watchlist_id, show_id=show_id).get_or_create(
        defaults={'watchlist_id': Watchlist.objects.get(pk=watchlist_id), 'show_id': ShowTable.objects.get(pk=show_id),
                  'status': new_status, 'added_date': date.today()}
    )

    # update the status if the object was found rather than created
    if not created:
        WatchlistShow.objects.filter(watchlist_id=watchlist_id, show_id=show_id).update(status=new_status)

    return HttpResponse(f'<span id="statusLabel">{new_status}</span>')


def get_high_rated_show_genre(user_id):
    highest_rated = History.objects.filter(user_id=user_id).order_by('-rating').first()

    if highest_rated:
        if highest_rated.show_id.movie:
            return highest_rated.show_id.movie.genre
        elif highest_rated.show_id.tv_series:
            return highest_rated.show_id.tv_series.genre


def recommend_similar_shows(user_id):
    genre_string = get_high_rated_show_genre(user_id)

    if not genre_string:
        return []

    eval_genre = literal_eval(genre_string)
    show_genres_set = set(eval_genre)

    reviewed_show_ids = History.objects.filter(user_id=user_id).values_list('show_id', flat=True)

    # Fetch all movies and TV shows, excluding those already reviewed
    movies = Movie.objects.exclude(movie_id__in=reviewed_show_ids)

    tv_shows = TvSeries.objects.exclude(tv_series_id__in=reviewed_show_ids)

    # Find movies and TV shows with at least 2 genres in common, excluding previously watched
    movies_common = [movie for movie in movies if len(set(literal_eval(movie.genre)) & show_genres_set) >= 1][:5]
    tv_shows_common = [tv_show for tv_show in tv_shows if len(set(literal_eval(tv_show.genre)) & show_genres_set) >= 1][
                      :5]

    for movie in movies_common:
        movie.show_type = "Movie"
        movie.show_id = ShowTable.objects.get(movie_id=movie.movie_id).show_id

    for tv_show in tv_shows_common:
        tv_show.show_type = "TV"
        tv_show.show_id = ShowTable.objects.get(tv_series_id=tv_show.tv_series_id).show_id

    # Combine the lists and sort by release date
    similar_shows = movies_common + tv_shows_common
    similar_shows = sorted(similar_shows, key=lambda x: x.release_date, reverse=True)[:10]

    return similar_shows


@require_POST
def submit_review(request):
    review_form = ReviewForm(request.POST)
    if review_form.is_valid():
        review = review_form.cleaned_data['review']
        rating = review_form.cleaned_data['rating']
        show_id = request.POST.get('show_id')
        History.objects.update_or_create(
            show_id=ShowTable.objects.get(pk=show_id),
            user_id=User.objects.get(pk=request.user.id),
            defaults={'rating': rating,
                      'review': review,
                      'review_date': date.today()}
        )

        context = {
            'user_review': {'review': review, 'rating': rating},  # Mimic the expected context structure
            'review_form': ReviewForm(),  # Provide a new blank form for future use
            'show_id': show_id  # Return the show ID to maintain context
        }

        return render(request, 'review_form.html', context)
